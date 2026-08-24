"""
Demonstrator Cell Shadingu (Toon Shading) w Pythonie + OpenGL
================================================================
Wymagania (instalacja):
    pip install pygame PyOpenGL PyOpenGL_accelerate numpy

Uruchomienie:
    python cell_shader_demo.py

Sterowanie:
    - Strzałki LEWO/PRAWO      -> obrót obiektu (yaw)
    - Strzałki GÓRA/DÓŁ        -> obrót obiektu (pitch)
    - Kółko myszy              -> zoom
    - SPACJA                   -> zmiana liczby poziomów cieniowania (2-6)
    - O                        -> włącz/wyłącz czarny kontur (outline)
    - ESC                      -> wyjście

Opis techniki:
    Cell shading (toon shading) polega na kwantyzacji oświetlenia
    do kilku dyskretnych poziomów jasności zamiast płynnego gradientu,
    co daje efekt "komiksowy" / rysunkowy. Dodatkowo dorysowywany jest
    czarny kontur (outline) metodą "backface expansion" - siatka jest
    powiększana wzdłuż normalnych i renderowana na czarno od tyłu.
"""

import sys
import math
import numpy as np
import pygame
from pygame.locals import DOUBLEBUF, OPENGL, KEYDOWN, K_ESCAPE, K_SPACE, K_o
from OpenGL.GL import *
from OpenGL.GL import shaders
from OpenGL.GLU import gluPerspective

# ---------------------------------------------------------------------------
# Generowanie siatki torusa (donut) - ładnie pokazuje cieniowanie na krzywiznach
# ---------------------------------------------------------------------------

def generate_torus(R=1.0, r=0.4, seg_major=48, seg_minor=24):
    verts = []
    norms = []
    indices = []

    for i in range(seg_major + 1):
        theta = 2.0 * math.pi * i / seg_major
        ct, st = math.cos(theta), math.sin(theta)
        for j in range(seg_minor + 1):
            phi = 2.0 * math.pi * j / seg_minor
            cp, sp = math.cos(phi), math.sin(phi)

            x = (R + r * cp) * ct
            y = (R + r * cp) * st
            z = r * sp

            nx = cp * ct
            ny = cp * st
            nz = sp

            verts.append((x, y, z))
            norms.append((nx, ny, nz))

    def idx(i, j):
        return i * (seg_minor + 1) + j

    for i in range(seg_major):
        for j in range(seg_minor):
            a = idx(i, j)
            b = idx(i + 1, j)
            c = idx(i + 1, j + 1)
            d = idx(i, j + 1)
            indices.extend([a, b, c, a, c, d])

    verts = np.array(verts, dtype=np.float32)
    norms = np.array(norms, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    return verts, norms, indices


# ---------------------------------------------------------------------------
# Shadery GLSL
# ---------------------------------------------------------------------------

VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform mat3 u_normal_mat;

out vec3 v_normal;
out vec3 v_frag_pos;

void main() {
    vec4 world_pos = u_model * vec4(in_position, 1.0);
    v_frag_pos = world_pos.xyz;
    v_normal = normalize(u_normal_mat * in_normal);
    gl_Position = u_proj * u_view * world_pos;
}
"""

# Fragment shader realizujący cel shading:
# - kwantyzacja komponentu diffuse na N poziomów (efekt "pasków" jasności)
# - twardy (nie rozmyty) highlight spekularny
# - rim light (podświetlenie krawędzi) dla efektu komiksowego
FRAGMENT_SHADER = """
#version 330 core
in vec3 v_normal;
in vec3 v_frag_pos;

uniform vec3 u_light_pos;
uniform vec3 u_view_pos;
uniform vec3 u_base_color;
uniform int u_levels;

out vec4 frag_color;

void main() {
    vec3 N = normalize(v_normal);
    vec3 L = normalize(u_light_pos - v_frag_pos);
    vec3 V = normalize(u_view_pos - v_frag_pos);
    vec3 H = normalize(L + V);

    // --- Kwantyzacja światła rozproszonego (diffuse) ---
    float diff = max(dot(N, L), 0.0);
    float levels = float(u_levels);
    float diff_q = floor(diff * levels) / levels;
    // lekkie podbicie minimalnego poziomu, by cień nie był czystą czernią
    diff_q = clamp(diff_q, 0.15, 1.0);

    // --- Twardy highlight spekularny (typowy dla cell shadingu) ---
    float spec = pow(max(dot(N, H), 0.0), 48.0);
    float spec_q = step(0.85, spec) * 0.6;

    // --- Rim light: podświetlenie krawędzi widocznych "pod kątem" do kamery ---
    float rim = 1.0 - max(dot(N, V), 0.0);
    float rim_q = smoothstep(0.6, 0.75, rim) * 0.35;

    vec3 color = u_base_color * diff_q + vec3(1.0) * spec_q + vec3(0.6, 0.8, 1.0) * rim_q;

    frag_color = vec4(color, 1.0);
}
"""

# Shader konturu - powiększona siatka renderowana na czarno "od tyłu"
OUTLINE_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 in_position;
layout(location = 1) in vec3 in_normal;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
uniform float u_outline_width;

void main() {
    vec3 expanded = in_position + in_normal * u_outline_width;
    gl_Position = u_proj * u_view * u_model * vec4(expanded, 1.0);
}
"""

OUTLINE_FRAGMENT_SHADER = """
#version 330 core
out vec4 frag_color;
void main() {
    frag_color = vec4(0.02, 0.02, 0.02, 1.0);
}
"""


def compile_program(vs_src, fs_src):
    vs = shaders.compileShader(vs_src, GL_VERTEX_SHADER)
    fs = shaders.compileShader(fs_src, GL_FRAGMENT_SHADER)
    return shaders.compileProgram(vs, fs)


def perspective(fovy, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m.T  # column-major dla OpenGL


def look_at(eye, target, up):
    eye, target, up = np.array(eye), np.array(target), np.array(up)
    f = (target - eye)
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)

    m = np.identity(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m.T


def rotation_y(angle):
    c, s = math.cos(angle), math.sin(angle)
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = c
    m[0, 2] = s
    m[2, 0] = -s
    m[2, 2] = c
    return m.T


def rotation_x(angle):
    c, s = math.cos(angle), math.sin(angle)
    m = np.identity(4, dtype=np.float32)
    m[1, 1] = c
    m[1, 2] = -s
    m[2, 1] = s
    m[2, 2] = c
    return m.T


def main():
    pygame.init()

    # Jawnie żądamy kontekstu OpenGL 3.3 Core Profile.
    # Bez tego niektóre sterowniki (zwłaszcza macOS, czasem starsze GPU/Linux)
    # tworzą kontekst compatibility, w którym shadery "#version 330 core"
    # nie zlinkują się poprawnie -> efekt: czarne, puste okno bez błędu.
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(
        pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
    )
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)

    width, height = 1000, 750
    pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("Demonstrator Cell Shadingu (Toon Shading) - PyOpenGL")

    # Diagnostyka - wypisz w konsoli jakiego kontekstu faktycznie użyto.
    print("GL_VERSION :", glGetString(GL_VERSION).decode())
    print("GL_RENDERER:", glGetString(GL_RENDERER).decode())
    print("GLSL       :", glGetString(GL_SHADING_LANGUAGE_VERSION).decode())

    glEnable(GL_DEPTH_TEST)
    glClearColor(0.08, 0.09, 0.12, 1.0)

    verts, norms, indices = generate_torus()
    vertex_data = np.hstack([verts, norms]).astype(np.float32)

    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)

    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, vertex_data.nbytes, vertex_data, GL_STATIC_DRAW)

    ebo = glGenBuffers(1)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

    stride = 6 * 4
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(3 * 4))
    glEnableVertexAttribArray(1)

    glBindVertexArray(0)

    try:
        toon_program = compile_program(VERTEX_SHADER, FRAGMENT_SHADER)
        outline_program = compile_program(OUTLINE_VERTEX_SHADER, OUTLINE_FRAGMENT_SHADER)
    except Exception as e:
        print("!!! Blad kompilacji/linkowania shaderow:")
        print(e)
        pygame.quit()
        sys.exit(1)

    err = glGetError()
    if err != GL_NO_ERROR:
        print("Uwaga - GL error po kompilacji shaderow:", err)

    proj = perspective(45.0, width / height, 0.1, 100.0)
    view = look_at(eye=(0, 1.6, 4.2), target=(0, 0, 0), up=(0, 1, 0))

    angle = 0.0
    pitch = 0.0
    auto_rotate_speed = 0.6
    levels = 4
    outline_enabled = True
    zoom = 4.2

    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                elif event.key == K_SPACE:
                    levels = levels + 1 if levels < 6 else 2
                elif event.key == K_o:
                    outline_enabled = not outline_enabled
            elif event.type == pygame.MOUSEWHEEL:
                zoom = max(2.0, min(10.0, zoom - event.y * 0.3))

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            angle -= 1.6 * dt
        if keys[pygame.K_RIGHT]:
            angle += 1 * dt
        if keys[pygame.K_UP]:
            pitch -= 1.2 * dt
        if keys[pygame.K_DOWN]:
            pitch += 1.2 * dt

        angle += auto_rotate_speed * dt
        view = look_at(eye=(0, 1.6, zoom), target=(0, 0, 0), up=(0, 1, 0))

        model = rotation_x(pitch) @ rotation_y(angle)
        normal_mat = np.ascontiguousarray(model[:3, :3], dtype=np.float32)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glBindVertexArray(vao)

        # --- Przebieg 1: kontur (outline) - rysujemy tylne ścianki powiększonej siatki ---
        if outline_enabled:
            glUseProgram(outline_program)
            glCullFace(GL_FRONT)
            glEnable(GL_CULL_FACE)
            glUniformMatrix4fv(glGetUniformLocation(outline_program, "u_model"), 1, GL_FALSE, model)
            glUniformMatrix4fv(glGetUniformLocation(outline_program, "u_view"), 1, GL_FALSE, view)
            glUniformMatrix4fv(glGetUniformLocation(outline_program, "u_proj"), 1, GL_FALSE, proj)
            glUniform1f(glGetUniformLocation(outline_program, "u_outline_width"), 0.025)
            glDrawElements(GL_TRIANGLES, len(indices), GL_UNSIGNED_INT, None)
            glDisable(GL_CULL_FACE)

        # --- Przebieg 2: właściwy cell shading ---
        glUseProgram(toon_program)
        glUniformMatrix4fv(glGetUniformLocation(toon_program, "u_model"), 1, GL_FALSE, model)
        glUniformMatrix4fv(glGetUniformLocation(toon_program, "u_view"), 1, GL_FALSE, view)
        glUniformMatrix4fv(glGetUniformLocation(toon_program, "u_proj"), 1, GL_FALSE, proj)
        glUniformMatrix3fv(glGetUniformLocation(toon_program, "u_normal_mat"), 1, GL_FALSE, normal_mat)
        glUniform3f(glGetUniformLocation(toon_program, "u_light_pos"), 3.0, 4.0, 3.0)
        glUniform3f(glGetUniformLocation(toon_program, "u_view_pos"), 0.0, 1.6, zoom)
        glUniform3f(glGetUniformLocation(toon_program, "u_base_color"), 0.95, 0.35, 0.35)
        glUniform1i(glGetUniformLocation(toon_program, "u_levels"), levels)

        glDrawElements(GL_TRIANGLES, len(indices), GL_UNSIGNED_INT, None)

        glBindVertexArray(0)
        pygame.display.flip()

        pygame.display.set_caption(
            f"Cell Shading Demo | poziomy: {levels} | kontur: {'ON' if outline_enabled else 'OFF'} | FPS: {clock.get_fps():.0f}"
        )

    pygame.quit()


if __name__ == "__main__":
    import ctypes
    main()
