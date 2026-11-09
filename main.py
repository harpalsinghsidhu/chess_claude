import os
import random
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget

# ------------------------------------------------------------ settings
LIGHT = (240, 217, 181)      # light squares (R, G, B)
DARK = (181, 136, 99)        # dark squares
START_DEPTH = 3              # AI level 1-4 at start


def col(t, a=255):
    return (t[0] / 255, t[1] / 255, t[2] / 255, a / 255)


START = ["rnbqkbnr", "pppppppp", "........", "........",
         "........", "........", "PPPPPPPP", "RNBQKBNR"]
VAL = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 20000}
KN = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
KG = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
DIAG = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
ORTH = [(-1, 0), (1, 0), (0, -1), (0, 1)]


# ------------------------------------------------------------ rules
class Pos:
    def __init__(self, b, w, cast, ep):
        self.b, self.w, self.cast, self.ep = b, w, cast, ep


def new_pos():
    return Pos([list(r) for r in START], True, {'K', 'Q', 'k', 'q'}, None)


def on(r, c):
    return 0 <= r < 8 and 0 <= c < 8


def attacked(b, r, c, by_white):
    pr = r + 1 if by_white else r - 1
    pawn = 'P' if by_white else 'p'
    for dc in (-1, 1):
        if on(pr, c + dc) and b[pr][c + dc] == pawn:
            return True
    knight = 'N' if by_white else 'n'
    for dr, dc in KN:
        if on(r + dr, c + dc) and b[r + dr][c + dc] == knight:
            return True
    king = 'K' if by_white else 'k'
    for dr, dc in KG:
        if on(r + dr, c + dc) and b[r + dr][c + dc] == king:
            return True
    for dirs, pcs in ((DIAG, 'BQ' if by_white else 'bq'), (ORTH, 'RQ' if by_white else 'rq')):
        for dr, dc in dirs:
            rr, cc = r + dr, c + dc
            while on(rr, cc):
                p = b[rr][cc]
                if p != '.':
                    if p in pcs:
                        return True
                    break
                rr += dr
                cc += dc
    return False


def gen(pos):
    b, w, out = pos.b, pos.w, []
    for r in range(8):
        for c in range(8):
            p = b[r][c]
            if p == '.' or p.isupper() != w:
                continue
            t = p.upper()
            if t == 'P':
                d = -1 if w else 1
                r2 = r + d
                if on(r2, c):
                    if b[r2][c] == '.':
                        out.append((r, c, r2, c))
                        if r == (6 if w else 1) and b[r + 2 * d][c] == '.':
                            out.append((r, c, r + 2 * d, c))
                    for dc in (-1, 1):
                        c2 = c + dc
                        if on(r2, c2):
                            q = b[r2][c2]
                            if (q != '.' and q.isupper() != w) or pos.ep == (r2, c2):
                                out.append((r, c, r2, c2))
            elif t in 'NK':
                for dr, dc in (KN if t == 'N' else KG):
                    r2, c2 = r + dr, c + dc
                    if on(r2, c2):
                        q = b[r2][c2]
                        if q == '.' or q.isupper() != w:
                            out.append((r, c, r2, c2))
                if t == 'K':
                    row = 7 if w else 0
                    if r == row and c == 4:
                        ks, qs, rook = ('K', 'Q', 'R') if w else ('k', 'q', 'r')
                        opp = not w
                        if (ks in pos.cast and b[row][5] == '.' and b[row][6] == '.'
                                and b[row][7] == rook
                                and not any(attacked(b, row, x, opp) for x in (4, 5, 6))):
                            out.append((row, 4, row, 6))
                        if (qs in pos.cast and b[row][1] == '.' and b[row][2] == '.'
                                and b[row][3] == '.' and b[row][0] == rook
                                and not any(attacked(b, row, x, opp) for x in (4, 3, 2))):
                            out.append((row, 4, row, 2))
            else:
                dirs = DIAG if t == 'B' else ORTH if t == 'R' else DIAG + ORTH
                for dr, dc in dirs:
                    r2, c2 = r + dr, c + dc
                    while on(r2, c2):
                        q = b[r2][c2]
                        if q == '.':
                            out.append((r, c, r2, c2))
                        else:
                            if q.isupper() != w:
                                out.append((r, c, r2, c2))
                            break
                        r2 += dr
                        c2 += dc
    return out


def apply(pos, m):
    r1, c1, r2, c2 = m
    b = [row[:] for row in pos.b]
    p = b[r1][c1]
    t = p.upper()
    cast = set(pos.cast)
    ep = None
    if t == 'P' and (r2, c2) == pos.ep and c1 != c2 and b[r2][c2] == '.':
        b[r1][c2] = '.'
    if t == 'P' and abs(r2 - r1) == 2:
        ep = ((r1 + r2) // 2, c1)
    b[r2][c2] = p
    b[r1][c1] = '.'
    if t == 'P' and r2 in (0, 7):
        b[r2][c2] = 'Q' if p.isupper() else 'q'
    if t == 'K' and abs(c2 - c1) == 2:
        if c2 > c1:
            b[r2][5], b[r2][7] = b[r2][7], '.'
        else:
            b[r2][3], b[r2][0] = b[r2][0], '.'
    for sq, rights in (((7, 4), 'KQ'), ((0, 4), 'kq'), ((7, 7), 'K'),
                       ((7, 0), 'Q'), ((0, 7), 'k'), ((0, 0), 'q')):
        if (r1, c1) == sq or (r2, c2) == sq:
            cast -= set(rights)
    return Pos(b, not pos.w, cast, ep)


def king_sq(b, white):
    k = 'K' if white else 'k'
    for r in range(8):
        for c in range(8):
            if b[r][c] == k:
                return r, c


def in_check(pos):
    r, c = king_sq(pos.b, pos.w)
    return attacked(pos.b, r, c, not pos.w)


def legal(pos):
    out = []
    for m in gen(pos):
        n = apply(pos, m)
        r, c = king_sq(n.b, pos.w)
        if not attacked(n.b, r, c, not pos.w):
            out.append(m)
    return out


# ------------------------------------------------------------ AI
def evaluate(pos):
    s = 0
    for r in range(8):
        for c in range(8):
            p = pos.b[r][c]
            if p == '.':
                continue
            t = p.upper()
            v = VAL[t]
            if t in 'NBPQ':
                v += int((3.5 - max(abs(r - 3.5), abs(c - 3.5))) * 6)
            if t == 'P':
                v += (6 - r) * 5 if p.isupper() else (r - 1) * 5
            s += v if p.isupper() else -v
    return s if pos.w else -s


def negamax(pos, depth, alpha, beta):
    if depth == 0:
        return evaluate(pos)
    moves = gen(pos)
    moves.sort(key=lambda m: -VAL.get(pos.b[m[2]][m[3]].upper(), 0))
    best = -10 ** 6
    for m in moves:
        if pos.b[m[2]][m[3]] in 'Kk':
            return 100000 + depth
        score = -negamax(apply(pos, m), depth - 1, -beta, -alpha)
        if score > best:
            best = score
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def best_move(pos, depth):
    moves = legal(pos)
    if not moves:
        return None
    random.shuffle(moves)
    moves.sort(key=lambda m: -VAL.get(pos.b[m[2]][m[3]].upper(), 0))
    best, best_m, alpha = -10 ** 9, moves[0], -10 ** 9
    for m in moves:
        score = -negamax(apply(pos, m), depth - 1, -10 ** 9, -alpha)
        if score > best:
            best, best_m = score, m
        alpha = max(alpha, best)
    return best_m


# ------------------------------------------------------------ game state
class Game:
    def __init__(self):
        self.depth = START_DEPTH
        self.version = 0          # bumped on every change so the screen knows to redraw
        self.reset()

    def reset(self):
        self.pos = new_pos()
        self.hist = []
        self.sel = None
        self.last = None
        self.thread = None
        self.result = [None]
        self.update()

    def update(self):
        self.moves = legal(self.pos)
        self.check = in_check(self.pos)
        self.over = None
        if not self.moves:
            if self.check:
                self.over = "Checkmate! " + ("Black" if self.pos.w else "White") + " wins"
            else:
                self.over = "Stalemate - draw"
        self.version += 1

    def play(self, m):
        self.hist.append((self.pos, self.last))
        self.pos = apply(self.pos, m)
        self.last = m
        self.sel = None
        self.update()

    def undo(self):
        if self.thread or not self.hist:
            return
        self.pos, self.last = self.hist.pop()
        while not self.pos.w and self.hist:
            self.pos, self.last = self.hist.pop()
        self.sel = None
        self.update()

    def click(self, r, c):
        if self.over or not self.pos.w or self.thread:
            return
        if self.sel:
            for m in self.moves:
                if m[:2] == self.sel and m[2:] == (r, c):
                    self.play(m)
                    return
        p = self.pos.b[r][c]
        self.sel = (r, c) if p != '.' and p.isupper() else None
        self.version += 1

    def think(self):
        if self.over or self.pos.w or self.thread:
            return
        pos, depth = self.pos, self.depth
        self.result = [None]
        res = self.result

        def job():
            res[0] = best_move(pos, depth)
        self.thread = threading.Thread(target=job, daemon=True)
        self.thread.start()
        self.version += 1

    def poll(self):
        if self.thread and not self.thread.is_alive():
            self.thread = None
            if self.result[0]:
                self.play(self.result[0])
            else:
                self.version += 1


# ------------------------------------------------------------ board widget
class Board(Widget):
    def __init__(self, game, **kw):
        super().__init__(**kw)
        self.g = game
        self.images = {}
        self.glyphs = {}
        self.load_images()
        self.bind(pos=self.redraw, size=self.redraw)

    def load_images(self):
        # optional: put wP.png ... bK.png in a "pieces" folder next to main.py
        folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pieces")
        for p in "PNBRQKpnbrqk":
            path = os.path.join(folder, ("w" if p.isupper() else "b") + p.upper() + ".png")
            if os.path.exists(path):
                try:
                    self.images[p] = CoreImage(path).texture
                except Exception:
                    pass

    def glyph(self, letter, size):
        key = (letter, size)
        if key not in self.glyphs:
            lab = CoreLabel(text=letter, font_size=size, bold=True)
            lab.refresh()
            self.glyphs[key] = lab.texture
        return self.glyphs[key]

    def geometry(self):
        sq = min(self.width, self.height) / 8
        x0 = self.x + (self.width - 8 * sq) / 2
        y0 = self.y + (self.height - 8 * sq) / 2
        return sq, x0, y0

    def redraw(self, *_):
        g = self.g
        sq, x0, y0 = self.geometry()
        if sq <= 0:
            return

        def cell(r, c):
            return (x0 + c * sq, y0 + (7 - r) * sq)

        self.canvas.clear()
        with self.canvas:
            for r in range(8):
                for c in range(8):
                    Color(*col(LIGHT if (r + c) % 2 == 0 else DARK))
                    Rectangle(pos=cell(r, c), size=(sq, sq))

            def tint(r, c, color):
                Color(*color)
                Rectangle(pos=cell(r, c), size=(sq, sq))

            if g.last:
                tint(g.last[0], g.last[1], col((255, 230, 0), 100))
                tint(g.last[2], g.last[3], col((255, 230, 0), 100))
            if g.check:
                r, c = king_sq(g.pos.b, g.pos.w)
                tint(r, c, col((255, 0, 0), 150))
            if g.sel:
                tint(g.sel[0], g.sel[1], col((0, 160, 255), 130))

            for r in range(8):
                for c in range(8):
                    p = g.pos.b[r][c]
                    if p == '.':
                        continue
                    x, y = cell(r, c)
                    if p in self.images:
                        Color(1, 1, 1, 1)
                        Rectangle(texture=self.images[p], pos=(x, y), size=(sq, sq))
                        continue
                    white = p.isupper()
                    cx, cy, rad = x + sq / 2, y + sq / 2, sq * 0.38
                    Color(*((0.96, 0.96, 0.96, 1) if white else (0.14, 0.14, 0.14, 1)))
                    Ellipse(pos=(cx - rad, cy - rad), size=(2 * rad, 2 * rad))
                    Color(*((0.08, 0.08, 0.08, 1) if white else (0.9, 0.9, 0.9, 1)))
                    Line(circle=(cx, cy, rad), width=dp(1.5))
                    tex = self.glyph(p.upper(), int(sq * 0.5))
                    Rectangle(texture=tex, pos=(cx - tex.width / 2, cy - tex.height / 2),
                              size=tex.size)

            if g.sel:
                for m in g.moves:
                    if m[:2] == g.sel:
                        x, y = cell(m[2], m[3])
                        cx, cy = x + sq / 2, y + sq / 2
                        if g.pos.b[m[2]][m[3]] != '.':
                            Color(0.85, 0.15, 0.15, 1)
                            Line(circle=(cx, cy, sq * 0.45), width=dp(2.5))
                        else:
                            Color(0.1, 0.55, 0.9, 0.9)
                            d = sq * 0.28
                            Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        sq, x0, y0 = self.geometry()
        c = int((touch.x - x0) // sq)
        r = 7 - int((touch.y - y0) // sq)
        if on(r, c):
            self.g.click(r, c)
        return True


# ------------------------------------------------------------ app
class ChessApp(App):
    def build(self):
        self.title = "Chess"
        Window.clearcolor = (0.11, 0.11, 0.11, 1)
        self.g = Game()
        self.seen = -1
        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
        self.status = Label(size_hint_y=None, height=dp(44), font_size=sp(17))
        self.board = Board(self.g)
        bar = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        for text, fn in (("New", self.new_game), ("Undo", self.undo),
                         ("Level -", lambda *_: self.level(-1)),
                         ("Level +", lambda *_: self.level(1))):
            bar.add_widget(Button(text=text, on_release=fn, font_size=sp(16)))
        root.add_widget(self.status)
        root.add_widget(self.board)
        root.add_widget(bar)
        Clock.schedule_interval(self.tick, 0.15)
        return root

    def new_game(self, *_):
        if not self.g.thread:
            self.g.reset()

    def undo(self, *_):
        self.g.undo()

    def level(self, d):
        self.g.depth = max(1, min(4, self.g.depth + d))
        self.seen = -1

    def tick(self, _dt):
        g = self.g
        g.think()
        g.poll()
        if g.over:
            text = g.over
        elif g.thread:
            text = "AI is thinking..."
        else:
            text = "Your move" + (" - CHECK!" if g.check else "")
        self.status.text = "%s     Level %d" % (text, g.depth)
        if g.version != self.seen:
            self.seen = g.version
            self.board.redraw()

    def on_pause(self):
        return True   # keep the app alive when you switch away

    def on_resume(self):
        pass


if __name__ == "__main__":
    ChessApp().run()
