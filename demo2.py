import sys
import math
import ctypes
import numpy as np
import pygame
from pygame.locals import DOUBLEBUF, OPENGL, KEYDOWN, K_ESCAPE, K_SPACE, K_o
from OpenGL.GL import *
from OpenGL.GL import shaders
from OpenGL.GLU import gluPerspective


# ---------------------------------------------------------------------------
# Zawartość okienka z instrukcją obsługi
# ---------------------------------------------------------------------------

INSTRUCTIONS_LINES = [
    ("title", "Instrukcja obsługi - Cell Shading Demo"),
    ("blank", ""),
    ("heading", "STEROWANIE OBIEKTEM"),
    ("normal", "Strzałki LEWO / PRAWO   -  obrót obiektu (yaw)"),
    ("normal", "Strzałki GÓRA / DÓŁ     -  obrót obiektu (pitch)"),
    ("normal", "Kółko myszy             -  przybliżanie / oddalanie (zoom)"),
    ("blank", ""),
    ("heading", "STEROWANIE ŚWIATŁEM"),
    ("normal", "W / S   -  przesuwanie światła w osi Z (przód / tył)"),
    ("normal", "A / D   -  przesuwanie światła w osi X (lewo / prawo)"),
    ("normal", "Q / E   -  przesuwanie światła w osi Y (dół / góra)"),
    ("normal", "R       -  reset pozycji światła do wartości domyślnej"),
    ("blank", ""),
    ("heading", "WYGLĄD I KSZTAŁT"),
    ("normal", "SPACJA  -  zmiana liczby poziomów cieniowania (2-6)"),
    ("normal", "O       -  włącz / wyłącz czarny kontur (outline)"),
    ("blank", ""),
]


def build_instructions_surface_data():
    fonts = {
        "title": pygame.font.SysFont("consolas,couriernew,monospace", 24, bold=True),
        "heading": pygame.font.SysFont("consolas,couriernew,monospace", 19, bold=True),
        "normal": pygame.font.SysFont("consolas,couriernew,monospace", 17),
        "hint": pygame.font.SysFont("consolas,couriernew,monospace", 15, italic=True),
    }
    colors = {
        "title": (255, 255, 255),
        "heading": (255, 190, 110),
        "normal": (222, 224, 232),
        "hint": (165, 172, 188),
    }

    line_gap = 5
    rendered = []
    max_w = 0
    total_h = 0
    for style, text in INSTRUCTIONS_LINES:
        if style == "blank":
            h = fonts["normal"].get_height() // 2
            rendered.append((None, h))
        else:
            surf = fonts[style].render(text, True, colors[style])
            rendered.append((surf, surf.get_height()))
            max_w = max(max_w, surf.get_width())
        total_h += rendered[-1][1] + line_gap
    total_h -= line_gap

    pad_x, pad_y = 32, 26
    surface_w = max_w + pad_x * 2
    surface_h = total_h + pad_y * 2

    canvas = pygame.Surface((surface_w, surface_h), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    y = pad_y
    for surf, h in rendered:
        if surf is not None:
            canvas.blit(surf, (pad_x, y))
        y += h + line_gap

    pixel_data = pygame.image.tostring(canvas, "RGBA", True)
    return pixel_data, surface_w, surface_h


def draw_instructions_popup(pixel_data, tex_w, tex_h, screen_w, screen_h):
    max_w = screen_w - 80
    max_h = screen_h - 80
    scale = min(max_w / tex_w, max_h / tex_h, 1.0)
    disp_w = tex_w * scale
    disp_h = tex_h * scale

    def to_ndc(px, py):
        return (px / screen_w) * 2.0 - 1.0, 1.0 - (py / screen_h) * 2.0

    def draw_quad(cx, cy, half_w, half_h, color):
        x0, y0 = to_ndc(cx - half_w, cy - half_h)
        x1, y1 = to_ndc(cx + half_w, cy + half_h)
        glColor4f(*color)
        glBegin(GL_QUADS)
        glVertex2f(x0, y0)
        glVertex2f(x1, y0)
        glVertex2f(x1, y1)
        glVertex2f(x0, y1)
        glEnd()

    draw_quad(screen_w / 2, screen_h / 2, screen_w / 2, screen_h / 2, (0.0, 0.0, 0.0, 0.45))
    draw_quad(screen_w / 2, screen_h / 2, disp_w / 2 + 10, disp_h / 2 + 10, (0.07, 0.08, 0.12, 0.92))

    left = screen_w / 2 - disp_w / 2
    bottom = screen_h / 2 + disp_h / 2
    ndc_x, ndc_y = to_ndc(left, bottom)
    glRasterPos2f(ndc_x, ndc_y)
    glPixelZoom(scale, scale)
    glDrawPixels(tex_w, tex_h, GL_RGBA, GL_UNSIGNED_BYTE, pixel_data)
    glPixelZoom(1.0, 1.0)
    glColor4f(1.0, 1.0, 1.0, 1.0)

# ---------------------------------------------------------------------------
# Generatory siatek - kilka różnych kształtów do wyboru
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


def generate_sphere_shaded(radius=1.15, stacks=20, slices=32):
    verts = []
    norms = []
    indices = []

    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        cphi, sphi = math.cos(phi), math.sin(phi)
        for j in range(slices + 1):
            theta = 2.0 * math.pi * j / slices
            ct, st = math.cos(theta), math.sin(theta)
            x, y, z = sphi * ct, cphi, sphi * st
            verts.append((radius * x, radius * y, radius * z))
            norms.append((x, y, z))

    def idx(i, j):
        return i * (slices + 1) + j

    for i in range(stacks):
        for j in range(slices):
            a = idx(i, j)
            b = idx(i + 1, j)
            c = idx(i + 1, j + 1)
            d = idx(i, j + 1)
            indices.extend([a, c, b, a, d, c])

    verts = np.array(verts, dtype=np.float32)
    norms = np.array(norms, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    return verts, norms, indices


def generate_cube(size=1.5):
    s = size / 2.0
    faces = [
        ((0, 0, 1), (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s)),      # +Z
        ((0, 0, -1), (s, -s, -s), (-s, -s, -s), (-s, s, -s), (s, s, -s)),  # -Z
        ((1, 0, 0), (s, -s, s), (s, -s, -s), (s, s, -s), (s, s, s)),      # +X
        ((-1, 0, 0), (-s, -s, -s), (-s, -s, s), (-s, s, s), (-s, s, -s)),  # -X
        ((0, 1, 0), (-s, s, s), (s, s, s), (s, s, -s), (-s, s, -s)),      # +Y
        ((0, -1, 0), (-s, -s, -s), (s, -s, -s), (s, -s, s), (-s, -s, s)),  # -Y
    ]

    verts = []
    norms = []
    indices = []
    for n, a, b, c, d in faces:
        base = len(verts)
        for v in (a, b, c, d):
            verts.append(v)
            norms.append(n)
        indices.extend([base, base + 1, base + 2, base, base + 2, base + 3])

    verts = np.array(verts, dtype=np.float32)
    norms = np.array(norms, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    return verts, norms, indices


def generate_cone(radius=0.95, height=1.7, segments=32):
    half_h = height / 2.0
    verts = []
    norms = []
    indices = []

    for i in range(segments + 1):
        theta = 2.0 * math.pi * i / segments
        ct, st = math.cos(theta), math.sin(theta)
        n = np.array([ct * height, radius, st * height], dtype=np.float64)
        n = n / np.linalg.norm(n)

        verts.append((radius * ct, -half_h, radius * st))
        norms.append(tuple(n))
        verts.append((0.0, half_h, 0.0))
        norms.append(tuple(n))

    for i in range(segments):
        base_i, apex_i = i * 2, i * 2 + 1
        base_next, apex_next = (i + 1) * 2, (i + 1) * 2 + 1
        indices.extend([base_i, apex_i, base_next])

    cap_center_idx = len(verts)
    verts.append((0.0, -half_h, 0.0))
    norms.append((0.0, -1.0, 0.0))

    cap_ring_start = len(verts)
    for i in range(segments + 1):
        theta = 2.0 * math.pi * i / segments
        ct, st = math.cos(theta), math.sin(theta)
        verts.append((radius * ct, -half_h, radius * st))
        norms.append((0.0, -1.0, 0.0))

    for i in range(segments):
        a = cap_center_idx
        b = cap_ring_start + i
        c = cap_ring_start + i + 1
        indices.extend([a, b, c])

    verts = np.array(verts, dtype=np.float32)
    norms = np.array(norms, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    return verts, norms, indices

# Znacznik źródła światła
def generate_sphere(radius=1.0, stacks=8, slices=8):
    verts = []
    indices = []

    for i in range(stacks + 1):
        phi = math.pi * i / stacks
        cphi, sphi = math.cos(phi), math.sin(phi)
        for j in range(slices + 1):
            theta = 2.0 * math.pi * j / slices
            ctheta, stheta = math.cos(theta), math.sin(theta)
            x = radius * sphi * ctheta
            y = radius * cphi
            z = radius * sphi * stheta
            verts.append((x, y, z))

    def idx(i, j):
        return i * (slices + 1) + j

    for i in range(stacks):
        for j in range(slices):
            a = idx(i, j)
            b = idx(i + 1, j)
            c = idx(i + 1, j + 1)
            d = idx(i, j + 1)
            indices.extend([a, b, c, a, c, d])

    verts = np.array(verts, dtype=np.float32)
    indices = np.array(indices, dtype=np.uint32)
    return verts, indices


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

    float diff = max(dot(N, L), 0.0);
    float levels = float(u_levels);
    float diff_q = floor(diff * levels) / levels;
    diff_q = clamp(diff_q, 0.15, 1.0);

    float spec = pow(max(dot(N, H), 0.0), 48.0);
    float spec_q = step(0.85, spec) * 0.6;

    float rim = 1.0 - max(dot(N, V), 0.0);
    float rim_q = smoothstep(0.6, 0.75, rim) * 0.35;

    vec3 color = u_base_color * diff_q + vec3(1.0) * spec_q + vec3(0.6, 0.8, 1.0) * rim_q;

    frag_color = vec4(color, 1.0);
}
"""

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

BACKGROUND_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 in_pos;
out float v_y;
void main() {
    v_y = in_pos.y;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

BACKGROUND_FRAGMENT_SHADER = """
#version 330 core
in float v_y;
uniform vec3 u_bottom_color;
uniform vec3 u_top_color;
uniform int u_band_count;
out vec4 frag_color;
void main() {
    float t = clamp(v_y * 0.5 + 0.5, 0.0, 1.0);
    float bands = float(u_band_count);
    float t_q = floor(t * bands) / max(bands - 1.0, 1.0);
    t_q = clamp(t_q, 0.0, 1.0);
    vec3 color = mix(u_bottom_color, u_top_color, t_q);
    float horizon_glow = smoothstep(0.35, 0.0, t) * 0.15;
    color += vec3(1.0, 0.85, 0.6) * horizon_glow;
    frag_color = vec4(color, 1.0);
}
"""

MARKER_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec3 in_position;
uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;
void main() {
    gl_Position = u_proj * u_view * u_model * vec4(in_position, 1.0);
}
"""

MARKER_FRAGMENT_SHADER = """
#version 330 core
uniform vec3 u_marker_color;
out vec4 frag_color;
void main() {
    frag_color = vec4(u_marker_color, 1.0);
}
"""

# używany do rysowania ikonek wyboru kształtu.
HUD_VERTEX_SHADER = """
#version 330 core
layout(location = 0) in vec2 in_pos;
void main() {
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

HUD_FRAGMENT_SHADER = """
#version 330 core
uniform vec4 u_color;
out vec4 frag_color;
void main() {
    frag_color = u_color;
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
    return m.T


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


def translation_scale(pos, scale=1.0):
    m = np.identity(4, dtype=np.float32)
    m[0, 0] = scale
    m[1, 1] = scale
    m[2, 2] = scale
    m[0, 3] = pos[0]
    m[1, 3] = pos[1]
    m[2, 3] = pos[2]
    return m.T


# ---------------------------------------------------------------------------
# Pomoce do rysowania interfejsu 2D: ikonki kształtów + wskaźnik światła
# ---------------------------------------------------------------------------

def pixel_to_ndc(px, py, width, height):
    ndc_x = (px / width) * 2.0 - 1.0
    ndc_y = 1.0 - (py / height) * 2.0
    return (ndc_x, ndc_y)


def circle_fan_ndc(cx, cy, radius, segments, width, height):
    pts = [pixel_to_ndc(cx, cy, width, height)]
    for i in range(segments + 1):
        theta = 2.0 * math.pi * i / segments
        pts.append(pixel_to_ndc(cx + radius * math.cos(theta), cy + radius * math.sin(theta), width, height))
    return pts  # GL_TRIANGLE_FAN


def square_fan_ndc(cx, cy, half, width, height):
    return rect_fan_ndc(cx, cy, half, half, width, height)


def rect_fan_ndc(cx, cy, half_w, half_h, width, height):
    corners = [
        (cx - half_w, cy - half_h), (cx + half_w, cy - half_h),
        (cx + half_w, cy + half_h), (cx - half_w, cy + half_h),
    ]
    pts = [pixel_to_ndc(cx, cy, width, height)] + [pixel_to_ndc(px, py, width, height) for px, py in corners]
    pts.append(pts[1])
    return pts  # GL_TRIANGLE_FAN


def triangle_tris_ndc(cx, cy, size, width, height):
    p1 = (cx, cy - size)
    p2 = (cx - size * 0.87, cy + size * 0.6)
    p3 = (cx + size * 0.87, cy + size * 0.6)
    return [pixel_to_ndc(*p1, width, height), pixel_to_ndc(*p2, width, height), pixel_to_ndc(*p3, width, height)]


def draw_hud_shape(program, points, color, mode):
    data = np.array(points, dtype=np.float32).flatten()
    vao = glGenVertexArrays(1)
    glBindVertexArray(vao)
    vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, data.nbytes, data, GL_DYNAMIC_DRAW)
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * 4, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glUseProgram(program)
    glUniform4f(glGetUniformLocation(program, "u_color"), *color)
    glDrawArrays(mode, 0, len(points))
    glBindVertexArray(0)
    glDeleteBuffers(1, [vbo])
    glDeleteVertexArrays(1, [vao])


def main():
    pygame.init()

    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
    pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_COMPATIBILITY)
    pygame.display.gl_set_attribute(pygame.GL_DEPTH_SIZE, 24)
    pygame.display.gl_set_attribute(pygame.GL_DOUBLEBUFFER, 1)

    width, height = 1000, 750
    pygame.display.set_mode((width, height), DOUBLEBUF | OPENGL)
    pygame.display.set_caption("Demonstrator Cell Shadingu (Toon Shading) - PyOpenGL")

    print("GL_VERSION :", glGetString(GL_VERSION).decode())
    print("GL_RENDERER:", glGetString(GL_RENDERER).decode())
    print("GLSL       :", glGetString(GL_SHADING_LANGUAGE_VERSION).decode())

    glEnable(GL_DEPTH_TEST)
    glClearColor(0.08, 0.09, 0.12, 1.0)

    # Wgrywanie siatek wszystkich dostępnych kształtów
    def upload_mesh(verts, norms, indices):
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
        return vao, len(indices)

    shapes = {
        "torus": upload_mesh(*generate_torus()),
        "sphere": upload_mesh(*generate_sphere_shaded()),
        "cube": upload_mesh(*generate_cube()),
        "cone": upload_mesh(*generate_cone()),
    }
    shape_order = ["torus", "sphere", "cube", "cone"]
    current_shape = "torus"

    # Tło
    bg_quad = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype=np.float32)
    bg_vao = glGenVertexArrays(1)
    glBindVertexArray(bg_vao)
    bg_vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, bg_vbo)
    glBufferData(GL_ARRAY_BUFFER, bg_quad.nbytes, bg_quad, GL_STATIC_DRAW)
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * 4, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glBindVertexArray(0)

    # Znacznik światła
    marker_verts, marker_indices = generate_sphere(radius=1.0, stacks=8, slices=8)
    marker_vao = glGenVertexArrays(1)
    glBindVertexArray(marker_vao)
    marker_vbo = glGenBuffers(1)
    glBindBuffer(GL_ARRAY_BUFFER, marker_vbo)
    glBufferData(GL_ARRAY_BUFFER, marker_verts.nbytes, marker_verts, GL_STATIC_DRAW)
    marker_ebo = glGenBuffers(1)
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, marker_ebo)
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, marker_indices.nbytes, marker_indices, GL_STATIC_DRAW)
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 3 * 4, ctypes.c_void_p(0))
    glEnableVertexAttribArray(0)
    glBindVertexArray(0)

    try:
        toon_program = compile_program(VERTEX_SHADER, FRAGMENT_SHADER)
        outline_program = compile_program(OUTLINE_VERTEX_SHADER, OUTLINE_FRAGMENT_SHADER)
        background_program = compile_program(BACKGROUND_VERTEX_SHADER, BACKGROUND_FRAGMENT_SHADER)
        marker_program = compile_program(MARKER_VERTEX_SHADER, MARKER_FRAGMENT_SHADER)
        hud_program = compile_program(HUD_VERTEX_SHADER, HUD_FRAGMENT_SHADER)
    except Exception as e:
        print("!!! Blad kompilacji/linkowania shaderow:")
        print(e)
        pygame.quit()
        sys.exit(1)

    err = glGetError()
    if err != GL_NO_ERROR:
        print("Uwaga - GL error po kompilacji shaderow:", err)

    instructions_data, instructions_w, instructions_h = build_instructions_surface_data()
    show_instructions = True

    fovy = 45.0
    aspect = width / height
    proj = perspective(fovy, aspect, 0.1, 100.0)

    angle = 0.0
    pitch = 0.0
    auto_rotate_speed = 0.06
    levels = 4
    outline_enabled = True
    zoom = 4.2

    default_light_pos = np.array([0.0, 1.5, 0.0], dtype=np.float32)
    light_pos = default_light_pos.copy()
    light_move_speed = 2.5
    show_light_marker = True

    bg_bottom_color = (0.55, 0.32, 0.28)
    bg_top_color = (0.16, 0.18, 0.32)
    bg_band_count = 6

    # Definicje ikonek wyboru kształtu 
    icon_size = 54
    icon_margin = 18
    icon_gap = 14
    icon_defs = []
    for i, name in enumerate(shape_order):
        cx = icon_margin + icon_size / 2 + i * (icon_size + icon_gap)
        cy = icon_margin + icon_size / 2
        icon_defs.append({"name": name, "cx": cx, "cy": cy, "half": icon_size / 2})

    panel_w = icon_margin * 2 + len(shape_order) * icon_size + (len(shape_order) - 1) * icon_gap
    panel_h = icon_margin * 2 + icon_size

    clock = pygame.time.Clock()
    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    if show_instructions:
                        show_instructions = False 
                    else:
                        running = False
                elif event.key == K_SPACE:
                    levels = levels + 1 if levels < 6 else 2
                elif event.key == K_o:
                    outline_enabled = not outline_enabled
                elif event.key == pygame.K_m:
                    show_light_marker = not show_light_marker
                elif event.key == pygame.K_r:
                    light_pos = default_light_pos.copy()
                elif event.key == pygame.K_h:
                    show_instructions = not show_instructions
            elif event.type == pygame.MOUSEWHEEL:
                zoom = max(2.0, min(10.0, zoom - event.y * 0.3))
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if show_instructions:
                    show_instructions = False  # kliknięcie gdziekolwiek zamyka pop-up
                else:
                    mx, my = event.pos
                    for icon in icon_defs:
                        if abs(mx - icon["cx"]) <= icon["half"] and abs(my - icon["cy"]) <= icon["half"]:
                            current_shape = icon["name"]
                            break

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            angle -= 1.6 * dt
        if keys[pygame.K_RIGHT]:
            angle += 1 * dt
        if keys[pygame.K_UP]:
            pitch -= 1.2 * dt
        if keys[pygame.K_DOWN]:
            pitch += 1.2 * dt

        if keys[pygame.K_w]:
            light_pos[2] -= light_move_speed * dt
        if keys[pygame.K_s]:
            light_pos[2] += light_move_speed * dt
        if keys[pygame.K_a]:
            light_pos[0] -= light_move_speed * dt
        if keys[pygame.K_d]:
            light_pos[0] += light_move_speed * dt
        if keys[pygame.K_e]:
            light_pos[1] += light_move_speed * dt
        if keys[pygame.K_q]:
            light_pos[1] -= light_move_speed * dt

        angle += auto_rotate_speed * dt
        eye = (0, 1.6, zoom)
        target = (0, 0, 0)
        up = (0, 1, 0)
        view = look_at(eye=eye, target=target, up=up)

        model = rotation_x(pitch) @ rotation_y(angle)
        normal_mat = np.ascontiguousarray(model[:3, :3], dtype=np.float32)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # Przebieg 0: tło
        glDisable(GL_DEPTH_TEST)
        glUseProgram(background_program)
        glUniform3f(glGetUniformLocation(background_program, "u_bottom_color"), *bg_bottom_color)
        glUniform3f(glGetUniformLocation(background_program, "u_top_color"), *bg_top_color)
        glUniform1i(glGetUniformLocation(background_program, "u_band_count"), bg_band_count)
        glBindVertexArray(bg_vao)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glBindVertexArray(0)
        glEnable(GL_DEPTH_TEST)

        shape_vao, shape_index_count = shapes[current_shape]
        glBindVertexArray(shape_vao)

        # Przebieg 1: kontur (outline)
        if outline_enabled:
            glUseProgram(outline_program)
            glCullFace(GL_FRONT)
            glEnable(GL_CULL_FACE)
            glUniformMatrix4fv(glGetUniformLocation(outline_program, "u_model"), 1, GL_FALSE, model)
            glUniformMatrix4fv(glGetUniformLocation(outline_program, "u_view"), 1, GL_FALSE, view)
            glUniformMatrix4fv(glGetUniformLocation(outline_program, "u_proj"), 1, GL_FALSE, proj)
            glUniform1f(glGetUniformLocation(outline_program, "u_outline_width"), 0.02)
            glDrawElements(GL_TRIANGLES, shape_index_count, GL_UNSIGNED_INT, None)
            glDisable(GL_CULL_FACE)

        # Przebieg 2: cell shading
        glUseProgram(toon_program)
        glUniformMatrix4fv(glGetUniformLocation(toon_program, "u_model"), 1, GL_FALSE, model)
        glUniformMatrix4fv(glGetUniformLocation(toon_program, "u_view"), 1, GL_FALSE, view)
        glUniformMatrix4fv(glGetUniformLocation(toon_program, "u_proj"), 1, GL_FALSE, proj)
        glUniformMatrix3fv(glGetUniformLocation(toon_program, "u_normal_mat"), 1, GL_FALSE, normal_mat)
        glUniform3f(glGetUniformLocation(toon_program, "u_light_pos"), *light_pos)
        glUniform3f(glGetUniformLocation(toon_program, "u_view_pos"), *eye)
        glUniform3f(glGetUniformLocation(toon_program, "u_base_color"), 0.95, 0.35, 0.35)
        glUniform1i(glGetUniformLocation(toon_program, "u_levels"), levels)
        glDrawElements(GL_TRIANGLES, shape_index_count, GL_UNSIGNED_INT, None)

        glBindVertexArray(0)

        # Przebieg 3: znacznik światła
        if show_light_marker:
            marker_model = translation_scale(light_pos, scale=0.12)
            glUseProgram(marker_program)
            glUniformMatrix4fv(glGetUniformLocation(marker_program, "u_model"), 1, GL_FALSE, marker_model)
            glUniformMatrix4fv(glGetUniformLocation(marker_program, "u_view"), 1, GL_FALSE, view)
            glUniformMatrix4fv(glGetUniformLocation(marker_program, "u_proj"), 1, GL_FALSE, proj)
            glUniform3f(glGetUniformLocation(marker_program, "u_marker_color"), 1.0, 0.9, 0.3)
            glBindVertexArray(marker_vao)
            glDrawElements(GL_TRIANGLES, len(marker_indices), GL_UNSIGNED_INT, None)
            glBindVertexArray(0)

        # Przebieg 4: HUD (ikonki kształtów + wskaźnik światła poza kadrem)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        # Panel pod ikonkami
        panel_pts = rect_fan_ndc(panel_w / 2, panel_h / 2, panel_w / 2, panel_h / 2, width, height)
        draw_hud_shape(hud_program, panel_pts, (0.05, 0.05, 0.09, 0.55), GL_TRIANGLE_FAN)

        for icon in icon_defs:
            selected = icon["name"] == current_shape
            if selected:
                glow_pts = square_fan_ndc(icon["cx"], icon["cy"], icon["half"] + 4, width, height)
                draw_hud_shape(hud_program, glow_pts, (1.0, 0.65, 0.3, 0.9), GL_TRIANGLE_FAN)

            base_color = (1.0, 0.95, 0.85, 1.0) if selected else (0.55, 0.57, 0.65, 1.0)
            r = icon["half"] * 0.62
            if icon["name"] == "sphere":
                pts = circle_fan_ndc(icon["cx"], icon["cy"], r, 24, width, height)
                draw_hud_shape(hud_program, pts, base_color, GL_TRIANGLE_FAN)
            elif icon["name"] == "torus":
                pts_outer = circle_fan_ndc(icon["cx"], icon["cy"], r, 24, width, height)
                draw_hud_shape(hud_program, pts_outer, base_color, GL_TRIANGLE_FAN)
                pts_inner = circle_fan_ndc(icon["cx"], icon["cy"], r * 0.45, 24, width, height)
                draw_hud_shape(hud_program, pts_inner, (0.05, 0.05, 0.09, 1.0), GL_TRIANGLE_FAN)
            elif icon["name"] == "cube":
                pts = square_fan_ndc(icon["cx"], icon["cy"], r, width, height)
                draw_hud_shape(hud_program, pts, base_color, GL_TRIANGLE_FAN)
            elif icon["name"] == "cone":
                pts = triangle_tris_ndc(icon["cx"], icon["cy"], r, width, height)
                draw_hud_shape(hud_program, pts, base_color, GL_TRIANGLES)

        # Pop-up z instrukcją obsługi
        if show_instructions:
            draw_instructions_popup(instructions_data, instructions_w, instructions_h, width, height)

        glDisable(GL_BLEND)
        glEnable(GL_DEPTH_TEST)

        pygame.display.flip()

        pygame.display.set_caption(
            "Cell Shading Demo | ksztalt: {} | poziomy: {} | kontur: {} | "
            "swiatlo: ({:.1f}, {:.1f}, {:.1f}) | FPS: {:.0f} | [H]=pomoc".format(
                current_shape,
                levels,
                "ON" if outline_enabled else "OFF",
                light_pos[0], light_pos[1], light_pos[2],
                clock.get_fps(),
            )
        )

    pygame.quit()


if __name__ == "__main__":
    main()