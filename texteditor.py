#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prosty edytor tekstu w Pythonie, renderowany przez OpenGL (pygame + PyOpenGL).

Funkcje:
  - kolorowanie składni (uproszczone, w stylu Pythona)
  - suwak (scrollbar) po prawej stronie do przewijania
  - zaznaczanie blokowe (kolumnowe) - przytrzymaj ALT i przeciągnij myszą
  - wyszukiwanie w tekście - Ctrl+F (Enter - następne, Shift+Enter - poprzednie, Esc - zamknij)
  - wybór czcionki i rozmiaru czcionki (pasek narzędzi na górze)
  - podstawowa edycja: zaznaczanie myszą i klawiaturą (Shift+strzałki), kopiuj/wytnij/wklej,
    Ctrl+A (zaznacz wszystko), Ctrl+S (zapisz), Ctrl+O (otwórz z argumentu / nowy plik)

Wymagania:
    pip install pygame PyOpenGL PyOpenGL_accelerate

Uruchomienie:
    python opengl_editor.py [ścieżka_do_pliku]
"""

import sys
import os
import re
import keyword as kw_module

import pygame
from pygame.locals import (
    QUIT, VIDEORESIZE, KEYDOWN, TEXTINPUT, MOUSEBUTTONDOWN, MOUSEBUTTONUP,
    MOUSEMOTION, MOUSEWHEEL, KMOD_CTRL, KMOD_SHIFT, KMOD_ALT,
    K_f, K_a, K_c, K_x, K_v, K_s, K_o, K_BACKSPACE, K_DELETE, K_RETURN,
    K_TAB, K_LEFT, K_RIGHT, K_UP, K_DOWN, K_HOME, K_END, K_PAGEUP, K_PAGEDOWN,
    K_ESCAPE, DOUBLEBUF, OPENGL, RESIZABLE,
)
from OpenGL.GL import (
    glViewport, glMatrixMode, glLoadIdentity, glOrtho, glClearColor, glClear,
    glEnable, glDisable, glBlendFunc, glBegin, glEnd, glVertex2f, glTexCoord2f,
    glColor4f, glGenTextures, glBindTexture, glTexParameteri, glTexImage2D,
    glDeleteTextures, glScissor,
    GL_PROJECTION, GL_MODELVIEW, GL_COLOR_BUFFER_BIT, GL_BLEND, GL_SRC_ALPHA,
    GL_ONE_MINUS_SRC_ALPHA, GL_TEXTURE_2D, GL_QUADS, GL_TEXTURE_MIN_FILTER,
    GL_TEXTURE_MAG_FILTER, GL_LINEAR, GL_RGBA, GL_UNSIGNED_BYTE, GL_SCISSOR_TEST,
)

try:
    import tkinter as _tk
    _HAS_TK = True
except Exception:
    _HAS_TK = False


# ============================================================== ustawienia

WIN_W, WIN_H = 1150, 760
TOOLBAR_H = 40
SEARCHBAR_H = 32
SCROLLBAR_W = 16
LINE_NUM_W = 58
MIN_WIN_W, MIN_WIN_H = 500, 300

BG_COLOR = (0.13, 0.14, 0.17)
TEXT_AREA_COLOR = (0.11, 0.12, 0.15)
TOOLBAR_COLOR = (0.18, 0.19, 0.23)
BUTTON_COLOR = (0.24, 0.26, 0.31)
BUTTON_HOVER = (0.30, 0.33, 0.40)
SCROLLBAR_BG = (0.16, 0.17, 0.20)
SCROLLBAR_FG = (0.35, 0.37, 0.45)
SCROLLBAR_FG_HOVER = (0.45, 0.47, 0.58)
SELECTION_COLOR = (0.25, 0.45, 0.75, 0.45)
CURRENT_LINE_COLOR = (1.0, 1.0, 1.0, 0.045)
CURSOR_COLOR = (1.0, 1.0, 1.0, 1.0)
LINE_NUM_COLOR = (110, 115, 130)
UI_TEXT_COLOR = (225, 225, 230)
SEARCH_MATCH_COLOR = (0.85, 0.7, 0.1, 0.40)
SEARCH_CURRENT_COLOR = (0.95, 0.5, 0.15, 0.65)

FONTS = [
    "Consolas", "Courier New", "DejaVu Sans Mono",
    "Liberation Mono", "Ubuntu Mono", "Cascadia Code",
    "Menlo", "Monaco",
]
FONT_SIZES = [12, 14, 16, 18, 20, 24, 28, 32]
DEFAULT_FONT_SIZE = 16

KEYWORDS = set(kw_module.kwlist)
BUILTINS = {
    "print", "len", "range", "str", "int", "float", "list", "dict", "set",
    "tuple", "self", "True", "False", "None", "open", "input", "enumerate",
    "zip", "map", "filter", "super", "object", "type", "isinstance",
    "Exception", "abs", "sum", "min", "max", "sorted", "reversed",
}

COLOR_KEYWORD = (140, 165, 240)
COLOR_BUILTIN = (140, 215, 225)
COLOR_STRING = (190, 190, 90)
COLOR_COMMENT = (110, 140, 110)
COLOR_NUMBER = (190, 140, 215)
COLOR_DEFAULT = (218, 218, 224)
COLOR_OP = (180, 180, 190)

TOKEN_REGEX = re.compile(r"""
    (?P<STRING>\"\"\".*?\"\"\"|'''.*?'''|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*') |
    (?P<COMMENT>\#.*$) |
    (?P<NUMBER>\b\d+\.?\d*\b) |
    (?P<NAME>[A-Za-z_][A-Za-z0-9_]*) |
    (?P<OP>[^\sA-Za-z0-9_]+)
""", re.VERBOSE)


def highlight_line(text):
    """Zwraca listę (fragment_tekstu, kolor_rgb) dla pojedynczej linii."""
    tokens = []
    pos = 0
    for m in TOKEN_REGEX.finditer(text):
        if m.start() > pos:
            tokens.append((text[pos:m.start()], COLOR_DEFAULT))
        group = m.lastgroup
        word = m.group()
        if group == "COMMENT":
            color = COLOR_COMMENT
        elif group == "STRING":
            color = COLOR_STRING
        elif group == "NUMBER":
            color = COLOR_NUMBER
        elif group == "NAME":
            if word in KEYWORDS:
                color = COLOR_KEYWORD
            elif word in BUILTINS:
                color = COLOR_BUILTIN
            else:
                color = COLOR_DEFAULT
        else:
            color = COLOR_OP
        tokens.append((word, color))
        pos = m.end()
    if pos < len(text):
        tokens.append((text[pos:], COLOR_DEFAULT))
    if not tokens:
        tokens.append(("", COLOR_DEFAULT))
    return tokens


# ============================================================== pomoce OpenGL

def surface_to_texture(surface):
    w, h = surface.get_size()
    data = pygame.image.tostring(surface, "RGBA", False)
    tex = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, data)
    glBindTexture(GL_TEXTURE_2D, 0)
    return tex, w, h


def draw_texture(tex, x, y, w, h):
    if w <= 0 or h <= 0:
        return
    glEnable(GL_TEXTURE_2D)
    glBindTexture(GL_TEXTURE_2D, tex)
    glColor4f(1, 1, 1, 1)
    glBegin(GL_QUADS)
    glTexCoord2f(0, 0); glVertex2f(x, y)
    glTexCoord2f(1, 0); glVertex2f(x + w, y)
    glTexCoord2f(1, 1); glVertex2f(x + w, y + h)
    glTexCoord2f(0, 1); glVertex2f(x, y + h)
    glEnd()
    glBindTexture(GL_TEXTURE_2D, 0)
    glDisable(GL_TEXTURE_2D)


def draw_rect(x, y, w, h, color):
    if len(color) == 4:
        r, g, b, a = color
    else:
        r, g, b = color
        a = 1.0
    glColor4f(r, g, b, a)
    glBegin(GL_QUADS)
    glVertex2f(x, y)
    glVertex2f(x + w, y)
    glVertex2f(x + w, y + h)
    glVertex2f(x, y + h)
    glEnd()


def point_in_rect(px, py, rect):
    rx, ry, rw, rh = rect
    return rx <= px <= rx + rw and ry <= py <= ry + rh


# ============================================================== edytor

class Editor:
    def __init__(self, filename=None):
        self.lines = [""]
        self.filename = filename
        if filename and os.path.isfile(filename):
            try:
                with open(filename, "r", encoding="utf-8") as fh:
                    content = fh.read()
                self.lines = content.split("\n") if content else [""]
            except Exception as exc:
                print("Nie udało się wczytać pliku:", exc)

        self.cursor_line = 0
        self.cursor_col = 0
        self.sel_anchor = None          # (line, col) - drugi koniec zaznaczenia
        self.is_block_selection = False

        self.scroll_line = 0.0
        self.win_w, self.win_h = WIN_W, WIN_H

        self.font_name = "DejaVu Sans Mono"
        if self.font_name not in FONTS:
            FONTS.insert(0, self.font_name)
        self.font_size = DEFAULT_FONT_SIZE
        self.font_cache = {}            # (name, size) -> pygame.font.Font
        self.line_tex_cache = {}        # text -> (font_key, tex, w, h)
        self.ui_font = pygame.font.SysFont(None, 20)
        self.ui_tex_cache = {}          # (text, color) -> (tex, w, h)

        self.dragging_scrollbar = False
        self.dragging_selection = False
        self.scrollbar_hover = False

        self.search_mode = False
        self.search_text = ""
        self.search_matches = []
        self.search_current = -1

        self.status_message = ""
        self.status_timer = 0.0
        self.cursor_blink_t = 0.0

        self._layout()

    # -------------------------------------------------- czcionki / tekstury

    def get_font(self):
        key = (self.font_name, self.font_size)
        f = self.font_cache.get(key)
        if f is None:
            path = pygame.font.match_font(self.font_name.replace(" ", ""))
            if not path:
                path = pygame.font.match_font(self.font_name)
            if path:
                f = pygame.font.Font(path, self.font_size)
            else:
                f = pygame.font.SysFont(self.font_name, self.font_size)
            self.font_cache[key] = f
        return f

    def clear_line_cache(self):
        for _key, (_fk, tex, _w, _h) in self.line_tex_cache.items():
            try:
                glDeleteTextures(int(tex))
            except Exception:
                pass
        self.line_tex_cache.clear()

    def get_line_texture(self, text):
        font_key = (self.font_name, self.font_size)
        entry = self.line_tex_cache.get(text)
        if entry and entry[0] == font_key:
            return entry[1], entry[2], entry[3]
        if entry:
            try:
                glDeleteTextures(int(entry[1]))
            except Exception:
                pass
        if len(self.line_tex_cache) > 3000:
            self.clear_line_cache()

        font = self.get_font()
        lh = font.get_linesize()
        if text == "":
            surf = pygame.Surface((1, lh), pygame.SRCALPHA)
        else:
            tokens = highlight_line(text)
            total_w = sum(font.size(t)[0] for t, _c in tokens) or 1
            surf = pygame.Surface((total_w, lh), pygame.SRCALPHA)
            x = 0
            for tok_text, color in tokens:
                if tok_text == "":
                    continue
                tok_surf = font.render(tok_text, True, color)
                surf.blit(tok_surf, (x, (lh - tok_surf.get_height()) // 2))
                x += tok_surf.get_width()
        tex, w, h = surface_to_texture(surf)
        self.line_tex_cache[text] = (font_key, tex, w, h)
        return tex, w, h

    def get_ui_texture(self, text, color=UI_TEXT_COLOR):
        key = (text, color)
        entry = self.ui_tex_cache.get(key)
        if entry:
            return entry
        surf = self.ui_font.render(text, True, color)
        tex, w, h = surface_to_texture(surf)
        self.ui_tex_cache[key] = (tex, w, h)
        return tex, w, h

    def draw_ui_text(self, x, y, text, color=UI_TEXT_COLOR):
        tex, w, h = self.get_ui_texture(text, color)
        draw_texture(tex, x, y, w, h)
        return w, h

    # -------------------------------------------------------------- layout

    def _layout(self):
        self.text_area_x = LINE_NUM_W
        self.text_area_y = TOOLBAR_H + (SEARCHBAR_H if self.search_mode else 0)
        self.text_area_w = max(10, self.win_w - LINE_NUM_W - SCROLLBAR_W)
        self.text_area_h = max(10, self.win_h - self.text_area_y)

        font = self.get_font()
        self.line_h = font.get_linesize()
        self.visible_lines = max(1, self.text_area_h // self.line_h)

        # przyciski paska narzędzi
        bx = 10
        by = (TOOLBAR_H - 24) // 2
        self.btn_font = (bx, by, 190, 24); bx += 200
        self.btn_size_minus = (bx, by, 24, 24); bx += 30
        self.btn_size_label = (bx, by, 40, 24); bx += 46
        self.btn_size_plus = (bx, by, 24, 24); bx += 34
        self.btn_open = (bx, by, 70, 24); bx += 78
        self.btn_save = (bx, by, 70, 24); bx += 78

        self.scrollbar_rect = (self.win_w - SCROLLBAR_W, self.text_area_y,
                                SCROLLBAR_W, self.text_area_h)

    def resize(self, w, h):
        self.win_w = max(MIN_WIN_W, w)
        self.win_h = max(MIN_WIN_H, h)
        self._layout()

    # ------------------------------------------------------------ pomocnicze

    def text_width(self, text):
        return self.get_font().size(text)[0]

    def col_x(self, line_text, col):
        col = max(0, min(len(line_text), col))
        return self.text_width(line_text[:col])

    def col_from_x(self, line_text, rel_x):
        if rel_x <= 0:
            return 0
        font = self.get_font()
        n = len(line_text)
        prev_w = 0
        for i in range(1, n + 1):
            w = font.size(line_text[:i])[0]
            if w >= rel_x:
                if rel_x - prev_w <= w - rel_x:
                    return i - 1
                return i
            prev_w = w
        return n

    def has_selection(self):
        return (not self.is_block_selection) and self.sel_anchor is not None \
            and self.sel_anchor != (self.cursor_line, self.cursor_col)

    def has_block_selection(self):
        return self.is_block_selection and self.sel_anchor is not None

    def clear_selection(self):
        self.sel_anchor = None
        self.is_block_selection = False

    def ordered_selection(self):
        a = self.sel_anchor
        b = (self.cursor_line, self.cursor_col)
        return (a, b) if a <= b else (b, a)

    def block_bounds(self):
        """Lista (line_idx, col_start, col_end) dla zaznaczenia blokowego."""
        if not self.has_block_selection():
            return []
        a_line, a_col = self.sel_anchor
        b_line, b_col = self.cursor_line, self.cursor_col
        x1 = self.col_x(self.lines[a_line], a_col)
        x2 = self.col_x(self.lines[b_line], b_col)
        xl, xr = min(x1, x2), max(x1, x2)
        l0, l1 = min(a_line, b_line), max(a_line, b_line)
        result = []
        for li in range(l0, l1 + 1):
            text = self.lines[li]
            c1 = self.col_from_x(text, xl)
            c2 = self.col_from_x(text, xr)
            result.append((li, min(c1, c2), max(c1, c2)))
        return result

    def set_status(self, msg):
        self.status_message = msg
        self.status_timer = 2.5

    # ------------------------------------------------------------- edycja

    def get_selected_text(self):
        if self.has_block_selection():
            parts = [self.lines[li][c1:c2] for li, c1, c2 in self.block_bounds()]
            return "\n".join(parts)
        if self.has_selection():
            (l1, c1), (l2, c2) = self.ordered_selection()
            if l1 == l2:
                return self.lines[l1][c1:c2]
            parts = [self.lines[l1][c1:]]
            parts.extend(self.lines[l1 + 1:l2])
            parts.append(self.lines[l2][:c2])
            return "\n".join(parts)
        return ""

    def delete_selection(self):
        if self.has_block_selection():
            bounds = self.block_bounds()
            for li, c1, c2 in bounds:
                self.lines[li] = self.lines[li][:c1] + self.lines[li][c2:]
            li0, c1_0, _c2 = bounds[0]
            self.cursor_line, self.cursor_col = li0, c1_0
            self.clear_selection()
            return True
        if self.has_selection():
            (l1, c1), (l2, c2) = self.ordered_selection()
            if l1 == l2:
                self.lines[l1] = self.lines[l1][:c1] + self.lines[l1][c2:]
            else:
                merged = self.lines[l1][:c1] + self.lines[l2][c2:]
                del self.lines[l1:l2 + 1]
                self.lines.insert(l1, merged)
            self.cursor_line, self.cursor_col = l1, c1
            self.clear_selection()
            return True
        return False

    def insert_text(self, text):
        if not text:
            return
        if self.has_selection() or self.has_block_selection():
            self.delete_selection()
        parts = text.split("\n")
        line = self.lines[self.cursor_line]
        before = line[:self.cursor_col]
        after = line[self.cursor_col:]
        if len(parts) == 1:
            self.lines[self.cursor_line] = before + parts[0] + after
            self.cursor_col += len(parts[0])
        else:
            self.lines[self.cursor_line] = before + parts[0]
            idx = self.cursor_line + 1
            for p in parts[1:-1]:
                self.lines.insert(idx, p)
                idx += 1
            self.lines.insert(idx, parts[-1] + after)
            self.cursor_line = idx
            self.cursor_col = len(parts[-1])
        self.ensure_cursor_visible()

    def backspace(self):
        if self.has_selection() or self.has_block_selection():
            self.delete_selection()
            return
        if self.cursor_col > 0:
            line = self.lines[self.cursor_line]
            self.lines[self.cursor_line] = line[:self.cursor_col - 1] + line[self.cursor_col:]
            self.cursor_col -= 1
        elif self.cursor_line > 0:
            prev_len = len(self.lines[self.cursor_line - 1])
            self.lines[self.cursor_line - 1] += self.lines[self.cursor_line]
            del self.lines[self.cursor_line]
            self.cursor_line -= 1
            self.cursor_col = prev_len
        self.ensure_cursor_visible()

    def delete_forward(self):
        if self.has_selection() or self.has_block_selection():
            self.delete_selection()
            return
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            self.lines[self.cursor_line] = line[:self.cursor_col] + line[self.cursor_col + 1:]
        elif self.cursor_line < len(self.lines) - 1:
            self.lines[self.cursor_line] += self.lines[self.cursor_line + 1]
            del self.lines[self.cursor_line + 1]

    # ------------------------------------------------------------ kursor

    def _maybe_anchor(self, shift):
        if shift:
            if self.sel_anchor is None or self.is_block_selection:
                self.sel_anchor = (self.cursor_line, self.cursor_col)
                self.is_block_selection = False
        else:
            self.clear_selection()

    def move_left(self, shift):
        self._maybe_anchor(shift)
        if self.cursor_col > 0:
            self.cursor_col -= 1
        elif self.cursor_line > 0:
            self.cursor_line -= 1
            self.cursor_col = len(self.lines[self.cursor_line])
        self.ensure_cursor_visible()

    def move_right(self, shift):
        self._maybe_anchor(shift)
        line = self.lines[self.cursor_line]
        if self.cursor_col < len(line):
            self.cursor_col += 1
        elif self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1
            self.cursor_col = 0
        self.ensure_cursor_visible()

    def move_up(self, shift, n=1):
        self._maybe_anchor(shift)
        self.cursor_line = max(0, self.cursor_line - n)
        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
        self.ensure_cursor_visible()

    def move_down(self, shift, n=1):
        self._maybe_anchor(shift)
        self.cursor_line = min(len(self.lines) - 1, self.cursor_line + n)
        self.cursor_col = min(self.cursor_col, len(self.lines[self.cursor_line]))
        self.ensure_cursor_visible()

    def move_home(self, shift):
        self._maybe_anchor(shift)
        self.cursor_col = 0
        self.ensure_cursor_visible()

    def move_end(self, shift):
        self._maybe_anchor(shift)
        self.cursor_col = len(self.lines[self.cursor_line])
        self.ensure_cursor_visible()

    def select_all(self):
        self.sel_anchor = (0, 0)
        self.is_block_selection = False
        self.cursor_line = len(self.lines) - 1
        self.cursor_col = len(self.lines[self.cursor_line])

    def ensure_cursor_visible(self):
        if self.cursor_line < self.scroll_line:
            self.scroll_line = float(self.cursor_line)
        elif self.cursor_line >= self.scroll_line + self.visible_lines:
            self.scroll_line = float(self.cursor_line - self.visible_lines + 1)
        self.clamp_scroll()

    def clamp_scroll(self):
        max_scroll = max(0, len(self.lines) - 1)
        self.scroll_line = max(0.0, min(float(max_scroll), self.scroll_line))

    # ------------------------------------------------------------ mysz

    def pixel_to_line_col(self, mx, my):
        rel_y = my - self.text_area_y
        line_idx = int(self.scroll_line) + max(0, int(rel_y // self.line_h))
        line_idx = max(0, min(len(self.lines) - 1, line_idx))
        rel_x = mx - self.text_area_x
        col = self.col_from_x(self.lines[line_idx], rel_x)
        return line_idx, col

    # ------------------------------------------------------------ schowek

    def _clipboard_get(self):
        try:
            if pygame.scrap.get_init():
                data = pygame.scrap.get(pygame.SCRAP_TEXT)
                if data:
                    return data.decode("utf-8", "ignore").replace("\x00", "")
        except Exception:
            pass
        if _HAS_TK:
            try:
                root = _tk.Tk()
                root.withdraw()
                text = root.clipboard_get()
                root.destroy()
                return text
            except Exception:
                return ""
        return ""

    def _clipboard_set(self, text):
        try:
            if pygame.scrap.get_init():
                pygame.scrap.put(pygame.SCRAP_TEXT, text.encode("utf-8"))
                return
        except Exception:
            pass
        if _HAS_TK:
            try:
                root = _tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update()
                root.destroy()
            except Exception:
                pass

    def copy(self):
        text = self.get_selected_text()
        if text:
            self._clipboard_set(text)
            self.set_status("Skopiowano")

    def cut(self):
        text = self.get_selected_text()
        if text:
            self._clipboard_set(text)
            self.delete_selection()
            self.set_status("Wycięto")

    def paste(self):
        text = self._clipboard_get()
        if text:
            self.insert_text(text)

    # ------------------------------------------------------------- plik

    def save_file(self):
        if not self.filename:
            self.filename = "nowy_plik.py"

        filename = self._get_available_filename(self.filename)

        try:
            with open(filename, "w", encoding="utf-8") as fh:
                fh.write("\n".join(self.lines))
            self.filename = filename  # <-- critical: persist the actual name used
            self.set_status("Zapisano: " + self.filename)
        except Exception as exc:
            self.set_status("Błąd zapisu: " + str(exc))

    def _get_available_filename(self, filename):
        if not os.path.exists(filename):
            return filename
        base, ext = os.path.splitext(filename)
        counter = 1
        if base[-1] < '0' or base[-1] > '9':
            new_filename = f"{base}_{counter}{ext}"
        else:
            new_filename = f"{base[:-2:]}_{counter}{ext}"
        while True:
            if not os.path.exists(new_filename):
                return new_filename
            new_filename = f"{base[:-2:]}_{counter}{ext}"
            counter += 1

    # ---------------------------------------------------------- wyszukiwanie

    def update_search(self):
        self.search_matches = []
        if self.search_text:
            pat = re.escape(self.search_text)
            for i, line in enumerate(self.lines):
                for m in re.finditer(pat, line, re.IGNORECASE):
                    self.search_matches.append((i, m.start(), m.end()))
        self.search_current = 0 if self.search_matches else -1
        if self.search_current >= 0:
            self.jump_to_match(self.search_current)

    def jump_to_match(self, idx):
        if not self.search_matches:
            return
        idx %= len(self.search_matches)
        self.search_current = idx
        line, c1, c2 = self.search_matches[idx]
        self.cursor_line, self.cursor_col = line, c2
        self.sel_anchor = (line, c1)
        self.is_block_selection = False
        self.ensure_cursor_visible()

    def search_next(self):
        if self.search_matches:
            self.jump_to_match(self.search_current + 1)

    def search_prev(self):
        if self.search_matches:
            self.jump_to_match(self.search_current - 1)


# ============================================================== renderowanie

def set_projection(w, h):
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(0, w, h, 0, -1, 1)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()


def render(ed):
    glClearColor(*BG_COLOR, 1.0)
    glClear(GL_COLOR_BUFFER_BIT)

    # tło obszaru tekstu
    draw_rect(0, ed.text_area_y, ed.win_w, ed.text_area_h, TEXT_AREA_COLOR)

    glEnable(GL_SCISSOR_TEST)
    glScissor(0, ed.win_h - (ed.text_area_y + ed.text_area_h), ed.win_w, ed.text_area_h)

    start_line = int(ed.scroll_line)
    frac_offset = (ed.scroll_line - start_line) * ed.line_h
    end_line = min(len(ed.lines), start_line + ed.visible_lines + 2)

    block_bounds = {li: (c1, c2) for li, c1, c2 in ed.block_bounds()} if ed.has_block_selection() else {}
    sel_range = None
    if ed.has_selection():
        (l1, c1), (l2, c2) = ed.ordered_selection()
        sel_range = (l1, c1, l2, c2)

    matches_by_line = {}
    for i, (li, c1, c2) in enumerate(ed.search_matches):
        matches_by_line.setdefault(li, []).append((c1, c2, i == ed.search_current))

    for idx in range(start_line, end_line):
        y = ed.text_area_y + (idx - start_line) * ed.line_h - frac_offset
        line_text = ed.lines[idx]

        if idx == ed.cursor_line and sel_range is None and not block_bounds:
            draw_rect(ed.text_area_x, y, ed.text_area_w, ed.line_h, CURRENT_LINE_COLOR)

        if idx in block_bounds:
            c1, c2 = block_bounds[idx]
            x1 = ed.col_x(line_text, c1)
            x2 = ed.col_x(line_text, c2) if c2 > c1 else x1 + 6
            draw_rect(ed.text_area_x + x1, y, max(2, x2 - x1), ed.line_h, SELECTION_COLOR)
        elif sel_range and sel_range[0] <= idx <= sel_range[2]:
            l1, c1, l2, c2 = sel_range
            lc1 = c1 if idx == l1 else 0
            lc2 = c2 if idx == l2 else len(line_text)
            x1 = ed.col_x(line_text, lc1)
            x2 = ed.col_x(line_text, lc2)
            if idx != l2:
                x2 = max(x2, x1 + 8)  # widoczny znacznik końca linii
            draw_rect(ed.text_area_x + x1, y, max(1, x2 - x1), ed.line_h, SELECTION_COLOR)

        for c1, c2, is_current in matches_by_line.get(idx, []):
            x1 = ed.col_x(line_text, c1)
            x2 = ed.col_x(line_text, c2)
            color = SEARCH_CURRENT_COLOR if is_current else SEARCH_MATCH_COLOR
            draw_rect(ed.text_area_x + x1, y, max(2, x2 - x1), ed.line_h, color)

        tex, w, h = ed.get_line_texture(line_text)
        draw_texture(tex, ed.text_area_x, y, w, h)

        num_tex, num_w, num_h = ed.get_ui_texture(str(idx + 1), LINE_NUM_COLOR)
        draw_texture(num_tex, LINE_NUM_W - num_w - 10, y + (ed.line_h - num_h) / 2, num_w, num_h)

        if idx == ed.cursor_line:
            ed.cursor_blink_t += 0
            if int(pygame.time.get_ticks() / 500) % 2 == 0:
                cx = ed.text_area_x + ed.col_x(line_text, ed.cursor_col)
                draw_rect(cx, y, 2, ed.line_h, CURSOR_COLOR)

    glDisable(GL_SCISSOR_TEST)

    # ---- suwak (scrollbar) ----
    sx, sy, sw, sh = ed.scrollbar_rect
    draw_rect(sx, sy, sw, sh, SCROLLBAR_BG)
    total_lines = max(1, len(ed.lines))
    thumb_h = max(24, sh * min(1.0, ed.visible_lines / total_lines))
    max_scroll = max(1, total_lines - ed.visible_lines)
    ratio = ed.scroll_line / max_scroll if max_scroll > 0 else 0
    thumb_y = sy + ratio * (sh - thumb_h)
    thumb_color = SCROLLBAR_FG_HOVER if (ed.dragging_scrollbar or ed.scrollbar_hover) else SCROLLBAR_FG
    draw_rect(sx + 3, thumb_y, sw - 6, thumb_h, thumb_color)

    # ---- pasek wyszukiwania ----
    if ed.search_mode:
        draw_rect(0, TOOLBAR_H, ed.win_w, SEARCHBAR_H, TOOLBAR_COLOR)
        ed.draw_ui_text(10, TOOLBAR_H + 7, "Szukaj (Enter: dalej, Shift+Enter: wstecz, Esc: zamknij):")
        box_x = 430
        draw_rect(box_x, TOOLBAR_H + 4, 300, SEARCHBAR_H - 8, (0.08, 0.08, 0.10))
        ed.draw_ui_text(box_x + 6, TOOLBAR_H + 7, ed.search_text or " ")
        if ed.search_text:
            count_txt = f"{ed.search_current + 1}/{len(ed.search_matches)}" if ed.search_matches else "0/0"
            ed.draw_ui_text(box_x + 310, TOOLBAR_H + 7, count_txt)

    # ---- pasek narzędzi ----
    draw_rect(0, 0, ed.win_w, TOOLBAR_H, TOOLBAR_COLOR)
    mx, my = pygame.mouse.get_pos()

    def button(rect, label, center=False):
        hovered = point_in_rect(mx, my, rect)
        draw_rect(*rect, BUTTON_HOVER if hovered else BUTTON_COLOR)
        tw, th = ed.ui_font.size(label)
        bx, by, bw, bh = rect
        tx = bx + (bw - tw) / 2 if center else bx + 6
        ty = by + (bh - th) / 2
        ed.draw_ui_text(tx, ty, label)

    button(ed.btn_font, "Czcionka: " + ed.font_name, center=True)
    button(ed.btn_size_minus, "-", center=True)
    button(ed.btn_size_label, str(ed.font_size), center=True)
    button(ed.btn_size_plus, "+", center=True)
    button(ed.btn_open, "Otwórz", center=True)
    button(ed.btn_save, "Zapisz", center=True)

    if ed.status_message and ed.status_timer > 0:
        ed.draw_ui_text(ed.btn_save[0] + ed.btn_save[2] + 20, 12, ed.status_message, (150, 220, 150))

    pygame.display.flip()


# ============================================================== główna pętla

def handle_toolbar_click(ed, mx, my):
    if point_in_rect(mx, my, ed.btn_font):
        idx = FONTS.index(ed.font_name) if ed.font_name in FONTS else 0
        ed.font_name = FONTS[(idx + 1) % len(FONTS)]
        ed.clear_line_cache()
        ed._layout()
        return True
    if point_in_rect(mx, my, ed.btn_size_minus):
        i = FONT_SIZES.index(ed.font_size) if ed.font_size in FONT_SIZES else 2
        ed.font_size = FONT_SIZES[max(0, i - 1)]
        ed.clear_line_cache()
        ed._layout()
        return True
    if point_in_rect(mx, my, ed.btn_size_plus):
        i = FONT_SIZES.index(ed.font_size) if ed.font_size in FONT_SIZES else 2
        ed.font_size = FONT_SIZES[min(len(FONT_SIZES) - 1, i + 1)]
        ed.clear_line_cache()
        ed._layout()
        return True
    if point_in_rect(mx, my, ed.btn_save):
        ed.save_file()
        return True
    if point_in_rect(mx, my, ed.btn_open):
        path = "".join(ed.lines)  # placeholder no-op if nic nie wpisano
        ed.set_status("Uruchom z argumentem: python opengl_editor.py plik.py")
        return True
    return False


def main():
    pygame.init()
    try:
        pygame.scrap.init()
    except Exception:
        pass
    pygame.key.start_text_input()

    filename = sys.argv[1] if len(sys.argv) > 1 else None
    screen = pygame.display.set_mode((WIN_W, WIN_H), DOUBLEBUF | OPENGL | RESIZABLE)
    pygame.display.set_caption("Prosty edytor tekstu (OpenGL)")

    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    set_projection(WIN_W, WIN_H)

    ed = Editor(filename)
    clock = pygame.time.Clock()
    running = True

    while running:
        dt = clock.tick(60) / 1000.0
        if ed.status_timer > 0:
            ed.status_timer -= dt

        for event in pygame.event.get():
            if event.type == QUIT:
                running = False

            elif event.type == VIDEORESIZE:
                ed.resize(event.w, event.h)
                pygame.display.set_mode((ed.win_w, ed.win_h), DOUBLEBUF | OPENGL | RESIZABLE)
                set_projection(ed.win_w, ed.win_h)

            elif event.type == KEYDOWN:
                mods = pygame.key.get_mods()
                ctrl = bool(mods & KMOD_CTRL)
                shift = bool(mods & KMOD_SHIFT)

                if ctrl and event.key == K_f:
                    ed.search_mode = not ed.search_mode
                    if not ed.search_mode:
                        ed.search_matches = []
                    ed._layout()
                    continue

                if ed.search_mode:
                    if event.key == K_ESCAPE:
                        ed.search_mode = False
                        ed.search_matches = []
                        ed._layout()
                    elif event.key == K_RETURN:
                        ed.search_prev() if shift else ed.search_next()
                    elif event.key == K_BACKSPACE:
                        ed.search_text = ed.search_text[:-1]
                        ed.update_search()
                    continue

                if ctrl and event.key == K_a:
                    ed.select_all()
                elif ctrl and event.key == K_c:
                    ed.copy()
                elif ctrl and event.key == K_x:
                    ed.cut()
                elif ctrl and event.key == K_v:
                    ed.paste()
                elif ctrl and event.key == K_s:
                    ed.save_file()
                elif ctrl and event.key == K_o:
                    pass
                elif event.key == K_BACKSPACE:
                    ed.backspace()
                elif event.key == K_DELETE:
                    ed.delete_forward()
                elif event.key == K_RETURN:
                    ed.insert_text("\n")
                elif event.key == K_TAB:
                    ed.insert_text("    ")
                elif event.key == K_LEFT:
                    ed.move_left(shift)
                elif event.key == K_RIGHT:
                    ed.move_right(shift)
                elif event.key == K_UP:
                    ed.move_up(shift)
                elif event.key == K_DOWN:
                    ed.move_down(shift)
                elif event.key == K_HOME:
                    ed.move_home(shift)
                elif event.key == K_END:
                    ed.move_end(shift)
                elif event.key == K_PAGEUP:
                    ed.move_up(shift, ed.visible_lines)
                    ed.scroll_line = max(0.0, ed.scroll_line - ed.visible_lines)
                elif event.key == K_PAGEDOWN:
                    ed.move_down(shift, ed.visible_lines)
                    ed.clamp_scroll()

            elif event.type == TEXTINPUT:
                if ed.search_mode:
                    ed.search_text += event.text
                    ed.update_search()
                else:
                    ed.insert_text(event.text)

            elif event.type == MOUSEBUTTONDOWN:
                mx, my = event.pos
                if event.button == 1:
                    if my < TOOLBAR_H:
                        handle_toolbar_click(ed, mx, my)
                    elif point_in_rect(mx, my, ed.scrollbar_rect):
                        ed.dragging_scrollbar = True
                        sx, sy, sw, sh = ed.scrollbar_rect
                        total_lines = max(1, len(ed.lines))
                        max_scroll = max(1, total_lines - ed.visible_lines)
                        ratio = max(0.0, min(1.0, (my - sy) / sh))
                        ed.scroll_line = ratio * max_scroll
                        ed.clamp_scroll()
                    elif my >= ed.text_area_y:
                        line, col = ed.pixel_to_line_col(mx, my)
                        ed.cursor_line, ed.cursor_col = line, col
                        mods = pygame.key.get_mods()
                        if mods & KMOD_ALT:
                            ed.is_block_selection = True
                            ed.sel_anchor = (line, col)
                        elif mods & KMOD_SHIFT and ed.sel_anchor is not None:
                            pass  # rozszerz istniejące zaznaczenie do klikniętego punktu
                        else:
                            ed.is_block_selection = False
                            ed.sel_anchor = (line, col)
                        ed.dragging_selection = True
                elif event.button == 4:
                    ed.scroll_line = max(0.0, ed.scroll_line - 3)
                    ed.clamp_scroll()
                elif event.button == 5:
                    ed.scroll_line += 3
                    ed.clamp_scroll()

            elif event.type == MOUSEBUTTONUP:
                if event.button == 1:
                    ed.dragging_scrollbar = False
                    ed.dragging_selection = False

            elif event.type == MOUSEMOTION:
                mx, my = event.pos
                ed.scrollbar_hover = point_in_rect(mx, my, ed.scrollbar_rect)
                if ed.dragging_scrollbar:
                    sx, sy, sw, sh = ed.scrollbar_rect
                    total_lines = max(1, len(ed.lines))
                    max_scroll = max(1, total_lines - ed.visible_lines)
                    ratio = max(0.0, min(1.0, (my - sy) / sh))
                    ed.scroll_line = ratio * max_scroll
                    ed.clamp_scroll()
                elif ed.dragging_selection:
                    cy = max(ed.text_area_y, min(ed.text_area_y + ed.text_area_h - 1, my))
                    line, col = ed.pixel_to_line_col(mx, cy)
                    ed.cursor_line, ed.cursor_col = line, col

            elif event.type == MOUSEWHEEL:
                ed.scroll_line -= event.y * 3
                ed.clamp_scroll()

        render(ed)

    pygame.quit()


if __name__ == "__main__":
    main()
