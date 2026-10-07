import threading
import socket
import json
import os
import time
import random
import colorsys
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.popup import Popup
from kivy.uix.behaviors import ButtonBehavior
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Line, Triangle, Rectangle
from kivy.uix.image import AsyncImage
import yt_dlp

# --- DETEKSI SISTEM OPERASI ANDROID NATIVE & MEDIA SESSION ---
IS_ANDROID = False
try:
    from jnius import autoclass, PythonJavaClass, java_method
    MediaPlayer = autoclass('android.media.MediaPlayer')
    AudioManager = autoclass('android.media.AudioManager')
    Equalizer = autoclass('android.media.audiofx.Equalizer')
    IS_ANDROID = True

    # --- NATIVE ANDROID ASYNC LISTENER ---
    class PyMediaListener(PythonJavaClass):
        __javainterfaces__ = [
            'android/media/MediaPlayer$OnPreparedListener',
            'android/media/MediaPlayer$OnCompletionListener',
            'android/media/MediaPlayer$OnErrorListener'
        ]
        __javacontext__ = 'app'

        def __init__(self, app_instance):
            super(PyMediaListener, self).__init__()
            self.app = app_instance

        @java_method('(Landroid/media/MediaPlayer;)V')
        def onPrepared(self, mp):
            Clock.schedule_once(self.app._on_prepared_callback, 0)

        @java_method('(Landroid/media/MediaPlayer;)V')
        def onCompletion(self, mp):
            Clock.schedule_once(self.app._handle_player_completion, 0)

        @java_method('(Landroid/media/MediaPlayer;II)Z')
        def onError(self, mp, what, extra):
            Clock.schedule_once(self.app._handle_player_error, 0)
            return True

    # --- LISTENER AUDIO FOCUS (notifikasi / telepon / aplikasi lain) ---
    class PyFocusListener(PythonJavaClass):
        __javainterfaces__ = ['android/media/AudioManager$OnAudioFocusChangeListener']
        __javacontext__ = 'app'

        def __init__(self, app_instance):
            super(PyFocusListener, self).__init__()
            self.app = app_instance

        @java_method('(I)V')
        def onAudioFocusChange(self, change):
            Clock.schedule_once(lambda dt: self.app._on_focus_change(change), 0)

except ImportError:
    pass

PLAYLIST_FILE = "playlist_yt.json"
EQ_CONFIG_FILE = "eq_yt.json"

# URL stream yt-dlp kadaluarsa; setelah jeda selebihnya (detik) stream dibuat ulang
STALE_PAUSE_SECONDS = 120
MAX_RETRY = 3

# --- KELAS LOADING OVERLAY CYBER ---
class CyberLoadingOverlay(FloatLayout):
    def __init__(self, cancel_cb=None, **kwargs):
        super(CyberLoadingOverlay, self).__init__(**kwargs)
        self.size_hint = (1, 1)
        self.pos_hint = {'x': 0, 'y': 0}

        with self.canvas.before:
            Color(0.05, 0.05, 0.08, 0.85)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self.update_canvas, size=self.update_canvas)

        box = BoxLayout(orientation='vertical', size_hint=(None, None), size=(dp(250), dp(150)), pos_hint={'center_x': 0.5, 'center_y': 0.5}, spacing=dp(15))

        self.lbl_icon = Label(text="[ | ]", font_size='35sp', color=(0, 0.95, 1, 1), size_hint_y=None, height=dp(40), bold=True)
        self.lbl_text = Label(text="MEMUAT AUDIO...", font_size='14sp', color=(0, 0.95, 1, 1), bold=True, size_hint_y=None, height=dp(20))

        box.add_widget(self.lbl_icon)
        box.add_widget(self.lbl_text)

        if cancel_cb:
            btn_cancel = CyberButton(
                text="BATAL", font_size='13sp', size_hint=(None, None), size=(dp(120), dp(40)),
                pos_hint={'center_x': 0.5}, bg_color=(0.6, 0.1, 0.2, 1), border_color=(1, 0.2, 0.3, 0.9)
            )
            btn_cancel.bind(on_press=lambda inst: cancel_cb())
            box.add_widget(btn_cancel)

        self.add_widget(box)

        self.anim_step = 0
        self.alpha = 1.0
        self.fade_dir = -1
        self.anim_event = Clock.schedule_interval(self._animate, 0.1)

    def update_canvas(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos): return True
        return super(CyberLoadingOverlay, self).on_touch_down(touch)

    def _animate(self, dt):
        self.alpha += 0.1 * self.fade_dir
        if self.alpha <= 0.3: self.fade_dir = 1
        elif self.alpha >= 1.0: self.fade_dir = -1
        self.lbl_text.color = (0, 0.95, 1, self.alpha)

        spin_chars = ["|", "/", "-", "\\"]
        self.anim_step = (self.anim_step + 1) % 4
        self.lbl_icon.text = f"[ {spin_chars[self.anim_step]} ]"

    def stop(self):
        if self.anim_event:
            self.anim_event.cancel()
            self.anim_event = None

# --- KOMPONEN UI ICON MURNI KANVAS ---
class CyberIconTextButton(ButtonBehavior, BoxLayout):
    def __init__(self, text="PUTAR", icon_type='play', bg_color=(0.1, 0.3, 0.7, 1), border_color=(0.3, 0.7, 1.0, 0.9), **kwargs):
        super(CyberIconTextButton, self).__init__(**kwargs)
        self.icon_type = icon_type
        self.bg_color = bg_color
        self.border_color = border_color

        self.orientation = 'horizontal'
        self.padding = [dp(22), 0, dp(4), 0]

        self.lbl = Label(text=text, font_size='11sp', bold=True, color=(1,1,1,1), halign='center', valign='middle')
        self.lbl.bind(size=self.lbl.setter('text_size'))

        self.add_widget(self.lbl)
        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

    def set_mode(self, mode):
        if mode == 'play':
            self.icon_type = 'play'
            self.lbl.text = "PUTAR"
            self.bg_color = (0.1, 0.3, 0.7, 1)
            self.border_color = (0.3, 0.7, 1.0, 0.9)
        elif mode == 'stop':
            self.icon_type = 'stop'
            self.lbl.text = "BERHENTI"
            self.bg_color = (0.8, 0.2, 0.2, 1)
            self.border_color = (1.0, 0.3, 0.3, 0.9)
        self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down':
                Color(min(1.0, self.bg_color[0] * 1.5), min(1.0, self.bg_color[1] * 1.5), min(1.0, self.bg_color[2] * 1.5), 1)
            else:
                Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])

            Color(*self.border_color)
            Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], dp(8)), width=dp(1.2))

            Color(1, 1, 1, 1)
            cx = self.x + dp(14)
            cy = self.center_y
            s = dp(10)

            if self.icon_type == 'play':
                Triangle(points=[cx - s*0.35, cy + s*0.45, cx - s*0.35, cy - s*0.45, cx + s*0.45, cy])
            elif self.icon_type == 'stop':
                Rectangle(pos=(cx - s*0.4, cy - s*0.4), size=(s*0.8, s*0.8))
            elif self.icon_type == 'search':
                Line(circle=(cx - dp(1), cy + dp(1), dp(3.5)), width=dp(1.2))
                Line(points=[cx + dp(1.5), cy - dp(1.5), cx + dp(4), cy - dp(4)], width=dp(1.5))

# --- TOMBOL UTAMA PLAY/PAUSE DENGAN EFEK BERKILAU (GLOW) ---
class MediaControlButton(ButtonBehavior, BoxLayout):
    def __init__(self, icon_type='play', bg_color=(0.11, 0.72, 0.33, 1), icon_color=(0,0,0,1), is_glow=False, **kwargs):
        super(MediaControlButton, self).__init__(**kwargs)
        self.icon_type = icon_type
        self.bg_color = list(bg_color)
        self.base_bg_color = list(bg_color)
        self.icon_color = icon_color
        self.is_glow = is_glow

        if self.is_glow:
            self.glow_hue = 0.3
            Clock.schedule_interval(self._animate_glow, 0.08)

        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

    def _animate_glow(self, dt):
        if not self.is_glow: return
        self.glow_hue += 0.03
        if self.glow_hue > 1.0: self.glow_hue = 0.0
        r, g, b = colorsys.hsv_to_rgb(self.glow_hue, 0.9, 1.0)
        self.bg_color = [r, g, b, 1.0]
        self.update_canvas()

    def set_icon(self, icon_type):
        self.icon_type = icon_type
        self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down':
                Color(self.bg_color[0]*0.7, self.bg_color[1]*0.7, self.bg_color[2]*0.7, self.bg_color[3])
            else:
                Color(*self.bg_color)

            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])

            Color(*self.icon_color)
            cx = self.x + self.width / 2.0; cy = self.y + self.height / 2.0; s = self.height * 0.4
            if self.icon_type == 'play': Triangle(points=[cx - s*0.35, cy + s*0.5, cx - s*0.35, cy - s*0.5, cx + s*0.5, cy])
            elif self.icon_type == 'pause':
                pw = s * 0.25; ph = s * 0.85; gap = s * 0.12
                Rectangle(pos=(cx - pw - gap, cy - ph/2), size=(pw, ph)); Rectangle(pos=(cx + gap, cy - ph/2), size=(pw, ph))
            elif self.icon_type == 'stop':
                st_s = s * 0.8
                Rectangle(pos=(cx - st_s/2, cy - st_s/2), size=(st_s, st_s))
            elif self.icon_type == 'next':
                Triangle(points=[cx - s*0.4, cy + s*0.45, cx - s*0.4, cy - s*0.45, cx + s*0.1, cy]); Rectangle(pos=(cx + s*0.15, cy - s*0.45), size=(s*0.2, s*0.9))

class CyberButton(ButtonBehavior, Label):
    def __init__(self, bg_color=(0.1, 0.12, 0.18, 1), border_color=(0, 0.8, 1, 0.6), **kwargs):
        super(CyberButton, self).__init__(**kwargs)
        self.bg_color = bg_color
        self.border_color = border_color
        self.bold = True
        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down': Color(min(1.0, self.bg_color[0] * 1.5), min(1.0, self.bg_color[1] * 1.5), min(1.0, self.bg_color[2] * 1.5), 1)
            else: Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            Color(*self.border_color)
            Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], dp(8)), width=dp(1.2))

class DeleteIcon(ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        super(DeleteIcon, self).__init__(**kwargs)
        self.size_hint = (None, None); self.size = (dp(35), dp(35)); self.pos_hint = {'center_y': 0.5}
        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down': Color(1, 0.2, 0.3, 0.8)
            else: Color(0.2, 0.1, 0.15, 0.8)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            Color(1, 0.2, 0.4, 1)
            margin = dp(10)
            Line(points=[self.x + margin, self.y + margin, self.right - margin, self.top - margin], width=dp(1.8), cap='round')
            Line(points=[self.right - margin, self.y + margin, self.x + margin, self.top - margin], width=dp(1.8), cap='round')

class PlayIcon(BoxLayout):
    def __init__(self, **kwargs):
        super(PlayIcon, self).__init__(**kwargs)
        self.size_hint = (None, None); self.size = (dp(12), dp(12)); self.pos_hint = {'center_y': 0.5}
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.11, 0.82, 0.43, 1)
            x, y = self.pos; w, h = self.size
            Triangle(points=[x, y + h, x, y, x + w, y + (h / 2.0)])

# --- ITEM PLAYLIST DENGAN EFEK TYPING BERGAYA TERMINAL ---
class PlaylistItem(ButtonBehavior, BoxLayout):
    def __init__(self, idx, title, url, play_cb, del_cb, is_active=False, **kwargs):
        super(PlaylistItem, self).__init__(**kwargs)
        self.orientation = 'horizontal'; self.size_hint_y = None; self.height = dp(65)
        self.padding = [dp(12), dp(10), dp(10), dp(10)]; self.spacing = dp(10); self.is_active = is_active

        self.full_status_text = "Memutar Lagu..." if is_active else "Streaming Audio YouTube"
        self.display_text = self.full_status_text if is_active else "Streaming Audio YouTube"
        self.typing_idx = 0
        self.typing_event = None

        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

        if is_active:
            icon_box = BoxLayout(size_hint_x=None, width=dp(16))
            icon_box.add_widget(PlayIcon()); self.add_widget(icon_box)

        text_box = BoxLayout(orientation='vertical', spacing=dp(2))
        title_color = (0.11, 0.82, 0.43, 1) if is_active else (0.95, 0.95, 0.95, 1)
        self.lbl_title = Label(text=title, font_size='15sp', color=title_color, bold=True, halign="left", valign="bottom", shorten=True, shorten_from='right')
        self.lbl_title.bind(size=self.lbl_title.setter('text_size'))

        sub_color = (0.11, 0.82, 0.43, 0.7) if is_active else (0.5, 0.6, 0.7, 1)
        self.lbl_sub = Label(text=self.display_text, font_size='11sp', color=sub_color, halign="left", valign="top")
        self.lbl_sub.bind(size=self.lbl_sub.setter('text_size'))

        text_box.add_widget(self.lbl_title); text_box.add_widget(self.lbl_sub)
        btn_del = DeleteIcon()
        btn_del.bind(on_press=lambda inst: del_cb())

        self.add_widget(text_box); self.add_widget(btn_del)
        self.idx = idx; self.url = url; self.title = title; self.play_cb = play_cb

        if is_active:
            # Mulai animasi typing
            self.display_text = ""
            self.typing_event = Clock.schedule_interval(self._animate_typing, 0.12)

    def _animate_typing(self, dt):
        if self.typing_idx < len(self.full_status_text):
            self.display_text += self.full_status_text[self.typing_idx]
            self.lbl_sub.text = self.display_text + "_"
            self.typing_idx += 1
        else:
            # Berkedip kursor akhir
            if self.lbl_sub.text.endswith("_"):
                self.lbl_sub.text = self.display_text
            else:
                self.lbl_sub.text = self.display_text + "_"

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down' or self.is_active: Color(0.15, 0.18, 0.22, 1)
            else: Color(0, 0, 0, 0)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])

    def on_release(self):
        if self.typing_event: self.typing_event.cancel()
        self.play_cb(self.url, self.title, self.idx)

# --- SLIDER EQ DENGAN GAUGE BAR BERKILAU (GLOW) ---
class CyberSlider(Slider):
    def __init__(self, track_color, **kwargs):
        super(CyberSlider, self).__init__(**kwargs)
        self.track_color = list(track_color)
        self.base_track_color = list(track_color)
        self.background_width = 0; self.value_track = False; self.cursor_size = (0, 0)

        # Animasi berkedip/berkilau pada gauge bar
        self.glow_phase = random.random() * 6.28
        Clock.schedule_interval(self._animate_gauge_glow, 0.05)

        self.bind(pos=self.update_canvas, size=self.update_canvas, value=self.update_canvas)

    def _animate_gauge_glow(self, dt):
        self.glow_phase += 0.2
        factor = 0.75 + 0.25 * (0.5 + 0.5 * random.random())
        self.track_color = [
            min(1.0, self.base_track_color[0] * factor),
            min(1.0, self.base_track_color[1] * factor),
            min(1.0, self.base_track_color[2] * factor),
            1.0
        ]
        self.update_canvas()

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            track_w = dp(6); cx = self.center_x; pad_y = dp(14)
            track_y = self.y + pad_y; track_h = self.height - (pad_y * 2)

            Color(0.2, 0.2, 0.25, 1)
            RoundedRectangle(pos=(cx - track_w/2, track_y), size=(track_w, track_h), radius=[dp(3)])

            cursor_y = self.value_pos[1]; fill_h = max(0, cursor_y - track_y)

            # Warna Gauge Bar Berkilau
            Color(*self.track_color)
            RoundedRectangle(pos=(cx - track_w/2, track_y), size=(track_w, fill_h), radius=[dp(3)])

            # Kursor Kustom
            Color(*self.track_color)
            RoundedRectangle(pos=(cx - dp(8), cursor_y - dp(8)), size=(dp(16), dp(16)), radius=[dp(8)])
            Color(0.1, 0.12, 0.18, 1)
            RoundedRectangle(pos=(cx - dp(6), cursor_y - dp(6)), size=(dp(12), dp(12)), radius=[dp(6)])
            Color(*self.track_color)
            RoundedRectangle(pos=(cx - dp(2.5), cursor_y - dp(2.5)), size=(dp(5), dp(5)), radius=[dp(2.5)])

class EQBand(BoxLayout):
    def __init__(self, theme_color, **kwargs):
        super(EQBand, self).__init__(**kwargs)
        self.theme_color = theme_color
        self.orientation = 'vertical'; self.spacing = dp(2); self.padding = [dp(2), dp(6), dp(2), dp(6)]
        self.bind(pos=self.update_canvas, size=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(self.theme_color[0], self.theme_color[1], self.theme_color[2], 0.05)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            Color(self.theme_color[0], self.theme_color[1], self.theme_color[2], 0.3)
            Line(rounded_rectangle=(self.x, self.y, self.width, self.height, dp(8)), width=dp(0.8))

class GraphicSpectrum(BoxLayout):
    def __init__(self, **kwargs):
        super(GraphicSpectrum, self).__init__(**kwargs)
        self.size_hint_y = None; self.height = dp(45); self.bars = 22; self.heights = [4.0] * self.bars
        self.bind(pos=self.draw_bars, size=self.draw_bars)

    def set_levels(self, new_heights):
        self.heights = new_heights
        self.draw_bars()

    def draw_bars(self, *args):
        self.canvas.clear()
        total_w = self.width; gap = dp(4)
        bar_w = max(dp(2), (total_w - (self.bars + 1) * gap) / self.bars)

        with self.canvas:
            for i in range(self.bars):
                bx = self.x + gap + i * (bar_w + gap)
                bh = max(dp(4), (self.heights[i] / 100.0) * (self.height - dp(4)))
                by = self.y + dp(2); ratio = i / self.bars
                r = 1.0 - (ratio * 0.8); g = 0.1 + (ratio * 0.9); b = 0.4 + (ratio * 0.6)
                Color(r, g, b, 0.95)
                RoundedRectangle(pos=(bx, by), size=(bar_w, bh), radius=[dp(2)])


class WinampCyberPlayer(App):
    def build(self):
        Window.clearcolor = (0.05, 0.05, 0.07, 1)
        Window.bind(on_keyboard=self.hook_media_keys)

        self.USE_ASYNC_LISTENER = False

        # --- STATE PEMULIHAN AUDIO (anti suara hilang) ---
        self.audio_mgr = None
        self.focus_listener = None
        self.wifi_lock = None
        self._paused_by_focus = False
        self._pause_time = 0.0
        self._last_pos = -1
        self._stall_count = 0
        self._resume_pos = 0
        self._retry_count = 0
        self._sound_event = None
        self._eq_session = None
        self._polling_attempts = 0

        if IS_ANDROID:
            self.player = MediaPlayer()
            self.player.setAudioStreamType(AudioManager.STREAM_MUSIC)

            try:
                self.mp_listener = PyMediaListener(self)
                self.player.setOnPreparedListener(self.mp_listener)
                self.player.setOnCompletionListener(self.mp_listener)
                self.player.setOnErrorListener(self.mp_listener)
                self.USE_ASYNC_LISTENER = True
            except Exception as e:
                pass

            self._init_audio_system()
            self.init_media_session()
        else:
            self.player = None

        self.is_paused = False
        self.is_playing = False
        self.media_has_started = False

        self.current_title = "SIAGA SISTEM"
        self.active_url = None
        self.current_index = -1
        self.results_container = None

        self.preview_task_id = 0
        self._current_ready_callback = None
        self.eq_event = None
        self.title_hue = 0.0

        self.playlist = self.load_playlist_data()
        self.init_equalizer()

        # ROOT LAYOUT
        main_layout = BoxLayout(orientation='vertical', padding=[dp(16), dp(16), dp(16), dp(16)], spacing=dp(12))

        # HEADER
        header_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(35))
        self.title_label = Label(text="YUTUFY by ridho", font_size='18sp', color=(1, 0.1, 0.3, 1), bold=True, halign="left")
        self.title_label.bind(size=self.title_label.setter('text_size'))

        btn_add_link = CyberIconTextButton(
            text="CARI", icon_type='search', size_hint_x=None, width=dp(95),
            bg_color=(0.1, 0.15, 0.25, 1), border_color=(0, 0.8, 1, 0.7)
        )
        btn_add_link.bind(on_press=self.open_add_popup)

        header_box.add_widget(self.title_label)
        header_box.add_widget(btn_add_link)
        main_layout.add_widget(header_box)
        Clock.schedule_interval(self._animate_title_color, 0.05)

        # NOW PLAYING PANEL LCD
        self.lcd_container = BoxLayout(orientation='vertical', padding=[dp(14), dp(10), dp(14), dp(10)], spacing=dp(6), size_hint_y=None, height=dp(145))
        self.lcd_container.bind(pos=self._update_lcd_canvas, size=self._update_lcd_canvas)

        self.lcd_mode = Label(text="SIAP STREAMING", font_size='11sp', color=(1, 0.4, 0.6, 0.8), size_hint_y=None, height=dp(16), halign="left")
        self.lcd_mode.bind(size=self.lcd_mode.setter('text_size'))

        self.status_label = Label(text="PILIH LAGU DARI DAFTAR PUTAR", font_size='13sp', color=(0, 0.95, 1, 1), bold=True, halign="center", valign="middle")
        self.status_label.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

        self.spectrum = GraphicSpectrum()
        self.lcd_container.add_widget(self.lcd_mode)
        self.lcd_container.add_widget(self.status_label)
        self.lcd_container.add_widget(self.spectrum)
        main_layout.add_widget(self.lcd_container)

        # KONTROL MEDIA IKON (DENGAN TOMBOL PLAY/PAUSE BERKILAU)
        control_grid = BoxLayout(orientation='horizontal', spacing=dp(15), padding=[dp(30), 0, dp(30), 0], size_hint_y=None, height=dp(55))

        self.btn_stop = MediaControlButton(icon_type='stop', bg_color=(0.2, 0.2, 0.25, 1), icon_color=(0.8, 0.8, 0.8, 1), is_glow=False)
        self.btn_stop.bind(on_press=self.stop_audio)

        # Tombol utama Play/Pause dibuat berkilau (is_glow=True)
        self.btn_play_pause = MediaControlButton(icon_type='play', bg_color=(0.11, 0.72, 0.33, 1), icon_color=(0, 0, 0, 1), size_hint_x=1.4, is_glow=True)
        self.btn_play_pause.bind(on_press=self.toggle_play_pause)

        self.btn_next = MediaControlButton(icon_type='next', bg_color=(0.2, 0.2, 0.25, 1), icon_color=(0.8, 0.8, 0.8, 1), is_glow=False)
        self.btn_next.bind(on_press=self.play_next)

        control_grid.add_widget(self.btn_stop)
        control_grid.add_widget(self.btn_play_pause)
        control_grid.add_widget(self.btn_next)
        main_layout.add_widget(control_grid)

        # EQUALIZER PANEL
        self.eq_container = BoxLayout(orientation='vertical', padding=[dp(10), dp(10), dp(10), dp(10)], spacing=dp(6), size_hint_y=None, height=dp(190))
        self.eq_container.bind(pos=self._update_eq_canvas, size=self._update_eq_canvas)

        eq_header = Label(text="EQUALISER DSP", font_size='11sp', color=(0.8, 0.8, 0.8, 1), bold=True, size_hint_y=None, height=dp(15))
        self.eq_container.add_widget(eq_header)

        eq_sliders = BoxLayout(orientation='horizontal', spacing=dp(10))
        self.eq_colors = [
            [1.0, 0.2, 0.4, 1], [0.8, 0.2, 1.0, 1], [0.3, 0.5, 1.0, 1], [0.0, 0.9, 1.0, 1], [0.2, 1.0, 0.4, 1],
        ]

        for i in range(self.eq_bands):
            band_box = EQBand(theme_color=self.eq_colors[i % len(self.eq_colors)])
            freq_hz = self.eq_freqs[i] / 1000.0
            freq_str = f"{freq_hz/1000:.1f}k" if freq_hz >= 1000 else f"{int(freq_hz)}"
            lbl_freq = Label(text=freq_str, font_size='10sp', color=(0.6, 0.7, 0.8, 1), size_hint_y=None, height=dp(14))
            db_val = self.eq_levels[i] / 100.0
            lbl_db = Label(text=f"{db_val:+.0f}dB", font_size='10sp', color=self.eq_colors[i % len(self.eq_colors)], bold=True, size_hint_y=None, height=dp(14))
            slider = CyberSlider(
                track_color=self.eq_colors[i % len(self.eq_colors)], orientation='vertical', min=self.eq_range[0], max=self.eq_range[1],
                value=self.eq_levels[i], step=100, size_hint_y=1
            )
            slider.bind(value=lambda instance, val, idx=i, lbl=lbl_db: self.on_eq_change(idx, val, lbl))

            band_box.add_widget(lbl_db)
            band_box.add_widget(slider)
            band_box.add_widget(lbl_freq)
            eq_sliders.add_widget(band_box)

        self.eq_container.add_widget(eq_sliders)
        main_layout.add_widget(self.eq_container)

        # PLAYLIST SCROLLVIEW
        playlist_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.playlist_container = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_y=None)
        self.playlist_container.bind(minimum_height=self.playlist_container.setter('height'))

        playlist_scroll.add_widget(self.playlist_container)
        main_layout.add_widget(playlist_scroll)

        self.refresh_playlist_ui()

        if not self.USE_ASYNC_LISTENER:
            Clock.schedule_interval(self._check_playback_finished_fallback, 1.0)

        # Watchdog: deteksi stream macet / suara hilang lalu pulihkan otomatis
        if IS_ANDROID:
            Clock.schedule_interval(self._watchdog, 2.0)

        return main_layout

    # ------------------------------------------------------------------
    #  SISTEM AUDIO ANDROID: WAKE LOCK, WIFI LOCK, AUDIO FOCUS
    # ------------------------------------------------------------------
    def _init_audio_system(self):
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            ctx = PythonActivity.mActivity.getApplicationContext()

            # CPU tetap hidup saat layar mati (butuh izin WAKE_LOCK)
            try:
                PowerManager = autoclass('android.os.PowerManager')
                self.player.setWakeMode(ctx, PowerManager.PARTIAL_WAKE_LOCK)
            except Exception:
                pass

            # WiFi tidak tidur saat streaming (butuh izin WAKE_LOCK)
            try:
                WifiManager = autoclass('android.net.wifi.WifiManager')
                wm = ctx.getSystemService(Context.WIFI_SERVICE)
                self.wifi_lock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "YUTUFY_WIFI")
                self.wifi_lock.setReferenceCounted(False)
            except Exception:
                self.wifi_lock = None

            # Audio focus
            self.audio_mgr = ctx.getSystemService(Context.AUDIO_SERVICE)
            self.focus_listener = PyFocusListener(self)
        except Exception:
            pass

    def _request_focus(self):
        if self.audio_mgr and self.focus_listener:
            try:
                # STREAM_MUSIC = 3, AUDIOFOCUS_GAIN = 1
                self.audio_mgr.requestAudioFocus(self.focus_listener, 3, 1)
            except Exception:
                pass
        if self.wifi_lock:
            try:
                if not self.wifi_lock.isHeld():
                    self.wifi_lock.acquire()
            except Exception:
                pass

    def _abandon_focus(self):
        if self.audio_mgr and self.focus_listener:
            try:
                self.audio_mgr.abandonAudioFocus(self.focus_listener)
            except Exception:
                pass
        if self.wifi_lock:
            try:
                if self.wifi_lock.isHeld():
                    self.wifi_lock.release()
            except Exception:
                pass

    def _on_focus_change(self, change):
        if not (IS_ANDROID and self.player):
            return
        try:
            if change == 1:  # AUDIOFOCUS_GAIN
                self.player.setVolume(1.0, 1.0)
                if self._paused_by_focus:
                    self._do_resume()
            elif change == -3:  # LOSS_TRANSIENT_CAN_DUCK
                self.player.setVolume(0.3, 0.3)
            elif change == -2:  # LOSS_TRANSIENT (telepon, notifikasi panjang)
                if self.is_playing and not self.is_paused:
                    self._do_pause(by_focus=True)
            elif change == -1:  # LOSS permanen (app musik lain)
                if self.is_playing and not self.is_paused:
                    self._do_pause(by_focus=False)
        except Exception:
            pass

    # ------------------------------------------------------------------
    #  PAUSE / RESUME / RESTREAM
    # ------------------------------------------------------------------
    def _do_pause(self, by_focus=False):
        if IS_ANDROID and self.player:
            try:
                if self.player.isPlaying(): self.player.pause()
            except Exception:
                pass
        self._pause_time = time.time()
        self._paused_by_focus = by_focus
        self.is_paused = True
        self.is_playing = False
        self.btn_play_pause.set_icon('play')
        self.set_status("Pemutaran DIJEDA", color=(1, 0.7, 0.1, 1), mode_info="STATUS: JEDA")
        self.update_lockscreen_widget('paused', self.current_title)

    def _do_resume(self):
        self._paused_by_focus = False
        stale = (time.time() - self._pause_time) > STALE_PAUSE_SECONDS

        if IS_ANDROID and self.player:
            if stale:
                # URL stream sudah kadaluarsa -> ambil ulang, lanjut dari posisi terakhir
                pos = 0
                try: pos = max(0, self.player.getCurrentPosition() - 500)
                except Exception: pass
                self.is_paused = False
                self._retry_count = 0
                self._restream(pos)
                return
            self._request_focus()
            try:
                self.player.setVolume(1.0, 1.0)
                self.player.start()
            except Exception:
                pos = 0
                try: pos = max(0, self.player.getCurrentPosition() - 500)
                except Exception: pass
                self.is_paused = False
                self._restream(pos)
                return

        self.is_paused = False
        self.is_playing = True
        self._last_pos = -1
        self._stall_count = 0
        self.btn_play_pause.set_icon('pause')
        self.set_status(f"DILANJUTKAN:\n{self.current_title[:35]}", color=(0, 1.0, 0.8, 1), mode_info="STATUS: MEMUTAR")
        self._start_visualizer()
        self.update_lockscreen_widget('playing', self.current_title)

    def _restream(self, resume_pos=0):
        """Ambil ulang URL audio untuk lagu aktif, lalu lanjut dari resume_pos (ms)."""
        if not self.active_url:
            return
        self._resume_pos = int(resume_pos) if resume_pos else 0
        self.start_stream_thread(
            custom_title=self.current_title,
            custom_url=self.active_url,
            index=self.current_index,
            on_ready_callback=self._current_ready_callback
        )

    def _try_recover(self):
        """Coba sambungkan ulang stream. Return True jika pemulihan dijalankan."""
        if not self.active_url or self._retry_count >= MAX_RETRY:
            return False
        self._retry_count += 1
        pos = 0
        try:
            if self.media_has_started and self.player:
                pos = max(0, self.player.getCurrentPosition() - 500)
            else:
                pos = max(0, self._last_pos - 500)
        except Exception:
            pos = max(0, self._last_pos - 500)
        self._stall_count = 0
        self._last_pos = -1
        self.set_status("MENYAMBUNG ULANG...", color=(1, 0.8, 0.2, 1), mode_info="PEMULIHAN AUDIO")
        self._restream(pos)
        return True

    def _watchdog(self, dt):
        if not (IS_ANDROID and self.player and self.is_playing
                and not self.is_paused and self.media_has_started):
            self._stall_count = 0
            self._last_pos = -1
            return
        try:
            pos = self.player.getCurrentPosition()
            playing = self.player.isPlaying()
            if (not playing) or pos == self._last_pos:
                self._stall_count += 1
            else:
                self._stall_count = 0
            self._last_pos = pos

            if self._stall_count >= 3:  # macet sekitar 6 detik
                self._stall_count = 0
                if not self._try_recover():
                    self._handle_player_error()
        except Exception:
            pass

    # ------------------------------------------------------------------
    #  CALLBACK PLAYER
    # ------------------------------------------------------------------
    def _on_prepared_callback(self, dt=0):
        if IS_ANDROID and self.player:
            try:
                self._request_focus()
                self.player.setVolume(1.0, 1.0)
                self._rebind_equalizer()

                if self._resume_pos:
                    try: self.player.seekTo(int(self._resume_pos))
                    except Exception: pass
                    self._resume_pos = 0

                self.player.start()
                self.media_has_started = True
                self.is_playing = True
                self.is_paused = False
                self._paused_by_focus = False
                self._last_pos = -1
                self._stall_count = 0
                self._start_visualizer()

                disp_title = self.current_title if len(self.current_title) < 70 else self.current_title[:70] + "..."
                self.set_status(disp_title, color=(0, 1.0, 0.8, 1), mode_info="MEMUTAR")

                self._polling_attempts = 0
                if self._sound_event:
                    self._sound_event.cancel()
                self._sound_event = Clock.schedule_interval(self._wait_for_actual_sound, 0.1)
                return
            except Exception:
                self._handle_player_error()
                return

        if self._current_ready_callback:
            self._current_ready_callback()
            self._current_ready_callback = None

    def _wait_for_actual_sound(self, dt):
        self._polling_attempts += 1

        if not self.is_playing:
            if self._current_ready_callback:
                self._current_ready_callback()
                self._current_ready_callback = None
            self._sound_event = None
            return False

        if IS_ANDROID and self.player:
            try:
                if self.player.isPlaying() and self.player.getCurrentPosition() > 50:
                    self._retry_count = 0  # suara terkonfirmasi, reset penghitung retry
                    if self._current_ready_callback:
                        self._current_ready_callback()
                        self._current_ready_callback = None
                    self._sound_event = None
                    return False

                if self._polling_attempts > 150:
                    self._sound_event = None
                    self._handle_player_error()
                    return False

                return True
            except Exception:
                self._sound_event = None
                self._handle_player_error()
                return False

        self._sound_event = None
        return False

    def _handle_player_error(self, dt=0):
        # Coba pulihkan dulu (mis. URL kadaluarsa) sebelum menyerah
        if self._try_recover():
            return

        self._retry_count = 0
        self.is_playing = False
        self.set_status("GALAT: STREAMING AUDIO GAGAL", color=(1, 0.3, 0.3, 1), mode_info="ERR // PEMUTAR")
        self._stop_visualizer()
        self.btn_play_pause.set_icon('play')
        self.reset_preview_buttons()

        if self._current_ready_callback:
            self._current_ready_callback()
            self._current_ready_callback = None

        if self.current_index != -1:
            Clock.schedule_once(lambda d: self.play_next(), 3.0)

    def _handle_player_completion(self, dt=0):
        # Jika "selesai" padahal lagu belum habis (koneksi putus), sambung ulang
        if IS_ANDROID and self.player and self.media_has_started:
            try:
                dur = self.player.getDuration()
                pos = self.player.getCurrentPosition()
                if dur > 0 and pos < (dur - 5000) and self._retry_count < MAX_RETRY:
                    self._try_recover()
                    return
            except Exception:
                pass

        self._retry_count = 0
        self.media_has_started = False
        self.is_playing = False
        self._stop_visualizer()
        self.btn_play_pause.set_icon('play')
        self.update_lockscreen_widget('stopped', self.current_title)
        self.reset_preview_buttons()

        if self.current_index != -1:
            Clock.schedule_once(lambda dt: self.play_next(), 0.5)

    def _check_playback_finished_fallback(self, dt):
        if not IS_ANDROID or not self.player: return
        if self.is_playing and not self.is_paused and self.media_has_started:
            try:
                if not self.player.isPlaying():
                    pos = self.player.getCurrentPosition()
                    dur = self.player.getDuration()
                    if dur > 0 and pos >= (dur - 2000):
                        self._handle_player_completion(dt)
            except: pass

    def reset_preview_buttons(self):
        if hasattr(self, 'results_container') and self.results_container:
            for widget in self.results_container.walk():
                if isinstance(widget, CyberIconTextButton) and widget.icon_type == 'stop':
                    widget.set_mode('play')

    def init_media_session(self):
        try:
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            MediaSession = autoclass('android.media.session.MediaSession')
            self.media_session = MediaSession(PythonActivity.mActivity, "YT_AUDIO_PLAYER")
            self.media_session.setActive(True)
        except Exception: pass

    def update_lockscreen_widget(self, state_str, title):
        if not IS_ANDROID or not hasattr(self, 'media_session'): return
        try:
            PlaybackState = autoclass('android.media.session.PlaybackState')
            state_builder = autoclass('android.media.session.PlaybackState$Builder')()
            state_builder.setActions(512 | 516 | 32 | 1)
            p_state = PlaybackState.STATE_STOPPED
            if state_str == 'playing': p_state = PlaybackState.STATE_PLAYING
            elif state_str == 'paused': p_state = PlaybackState.STATE_PAUSED
            state_builder.setState(p_state, -1, 1.0)
            self.media_session.setPlaybackState(state_builder.build())

            MediaMetadata = autoclass('android.media.MediaMetadata')
            meta_builder = autoclass('android.media.MediaMetadata$Builder')()
            meta_builder.putString(MediaMetadata.METADATA_KEY_TITLE, title)
            meta_builder.putString(MediaMetadata.METADATA_KEY_ARTIST, "Pemutar Audio YT")
            self.media_session.setMetadata(meta_builder.build())
        except Exception: pass

    def hook_media_keys(self, window, key, scancode, codepoint, modifier):
        PLAY_PAUSE_KEYS = [85, 126, 127, 1073742092]
        NEXT_KEYS = [87, 1073742095]; STOP_KEYS = [86, 1073742093]
        if key in PLAY_PAUSE_KEYS or scancode in PLAY_PAUSE_KEYS:
            self.toggle_play_pause(); return True
        elif key in NEXT_KEYS or scancode in NEXT_KEYS:
            self.play_next(); return True
        elif key in STOP_KEYS or scancode in STOP_KEYS:
            self.stop_audio(); return True
        return False

    def _animate_title_color(self, dt):
        self.title_hue += 0.01
        if self.title_hue > 1.0: self.title_hue = 0.0
        r, g, b = colorsys.hsv_to_rgb(self.title_hue, 0.8, 1.0)
        self.title_label.color = (r, g, b, 1)

    # ------------------------------------------------------------------
    #  EQUALIZER
    # ------------------------------------------------------------------
    def init_equalizer(self):
        self.eq_bands = 5; self.eq_range = [-1500, 1500]
        self.eq_freqs = [60000, 230000, 910000, 3600000, 14000000]
        self.eq_levels = [0, 0, 0, 0, 0]; self.eq_instance = None
        if IS_ANDROID and self.player:
            try:
                sid = self.player.getAudioSessionId()
                self.eq_instance = Equalizer(0, sid)
                self._eq_session = sid
                self.eq_instance.setEnabled(True)
                self.eq_bands = self.eq_instance.getNumberOfBands()
                self.eq_range = self.eq_instance.getBandLevelRange()
                self.eq_freqs = [self.eq_instance.getCenterFreq(i) for i in range(self.eq_bands)]
                self.eq_levels = [0] * self.eq_bands
            except Exception: pass

        if os.path.exists(EQ_CONFIG_FILE):
            try:
                with open(EQ_CONFIG_FILE, 'r') as f: saved_eq = json.load(f)
                if len(saved_eq) == self.eq_bands: self.eq_levels = saved_eq
            except: pass

        if self.eq_instance:
            for i in range(self.eq_bands):
                try: self.eq_instance.setBandLevel(i, self.eq_levels[i])
                except: pass

    def _rebind_equalizer(self):
        """Pastikan EQ tetap menempel ke audio session setelah reset()/prepare."""
        if not (IS_ANDROID and self.player):
            return
        try:
            sid = self.player.getAudioSessionId()
            if self.eq_instance is None or sid != self._eq_session:
                if self.eq_instance:
                    try: self.eq_instance.release()
                    except Exception: pass
                self.eq_instance = Equalizer(0, sid)
                self._eq_session = sid
            self.eq_instance.setEnabled(True)
            for i in range(self.eq_bands):
                try: self.eq_instance.setBandLevel(i, self.eq_levels[i])
                except Exception: pass
        except Exception:
            pass

    def on_eq_change(self, band_idx, value, label_widget):
        val_int = int(value)
        self.eq_levels[band_idx] = val_int
        label_widget.text = f"{val_int / 100.0:+.0f}dB"
        if self.eq_instance:
            try: self.eq_instance.setBandLevel(band_idx, val_int)
            except: pass
        try:
            with open(EQ_CONFIG_FILE, 'w') as f: json.dump(self.eq_levels, f)
        except: pass

    def _update_eq_canvas(self, *args):
        self.eq_container.canvas.before.clear()
        with self.eq_container.canvas.before:
            Color(0.08, 0.08, 0.1, 1)
            RoundedRectangle(pos=self.eq_container.pos, size=self.eq_container.size, radius=[dp(8)])
            Color(0.4, 0.4, 0.5, 0.5)
            Line(rounded_rectangle=(self.eq_container.x, self.eq_container.y, self.eq_container.width, self.eq_container.height, dp(8)), width=dp(0.8))

    def _update_lcd_canvas(self, *args):
        self.lcd_container.canvas.before.clear()
        with self.lcd_container.canvas.before:
            Color(0.06, 0.08, 0.12, 1)
            RoundedRectangle(pos=self.lcd_container.pos, size=self.lcd_container.size, radius=[dp(12)])
            Color(0, 0.8, 1, 0.7)
            Line(rounded_rectangle=(self.lcd_container.x, self.lcd_container.y, self.lcd_container.width, self.lcd_container.height, dp(12)), width=dp(1.2))

    def _update_spectrum_tick(self, dt):
        if self.is_playing and not self.is_paused:
            new_levels = [random.randint(15, 95) for _ in range(self.spectrum.bars)]
        else: new_levels = [3.0] * self.spectrum.bars
        self.spectrum.set_levels(new_levels)

    def _start_visualizer(self):
        if not self.eq_event: self.eq_event = Clock.schedule_interval(self._update_spectrum_tick, 0.1)

    def _stop_visualizer(self):
        if self.eq_event:
            self.eq_event.cancel()
            self.eq_event = None
        self.spectrum.set_levels([3.0] * self.spectrum.bars)

    def set_status(self, text, color=(0.1, 1.0, 0.3, 1), mode_info="STATUS: AKTIF"):
        def _update(dt):
            self.status_label.text = text
            self.status_label.color = color
            self.lcd_mode.text = mode_info
        Clock.schedule_once(_update)

    def check_internet(self):
        try:
            socket.setdefaulttimeout(3.0)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
            return True
        except: return False

    # ------------------------------------------------------------------
    #  KONTROL PEMUTARAN
    # ------------------------------------------------------------------
    def toggle_play_pause(self, instance=None):
        if not self.active_url:
            if self.playlist: self.play_next(None)
            else: self.set_status("TAMBAHKAN LAGU\nKE DAFTAR PUTAR", color=(1, 0.4, 0.4, 1), mode_info="GALAT // TANPA_URL")
            return

        if self.is_playing and not self.is_paused:
            self._do_pause(by_focus=False)

        elif self.is_paused:
            self._do_resume()

        else:
            self._retry_count = 0
            self.start_stream_thread(custom_title=self.current_title, custom_url=self.active_url, index=self.current_index)

    def start_stream_thread(self, custom_title=None, custom_url=None, index=-1, on_ready_callback=None, task_id=None):
        self._current_ready_callback = on_ready_callback
        self.preview_task_id = task_id if task_id is not None else random.randint(1000, 9999)

        if custom_url:
            self.active_url = custom_url
            self.current_title = custom_title if custom_title else "STREAM LANGSUNG"
            self.current_index = index
            self.refresh_playlist_ui()

        if not self.active_url:
            if self._current_ready_callback:
                self._current_ready_callback()
                self._current_ready_callback = None
            return

        if IS_ANDROID and self.player:
            try:
                if self.player.isPlaying() or self.is_paused:
                    self.player.stop()
            except: pass

        self.is_playing = False
        self.is_paused = False
        self.media_has_started = False
        self._stop_visualizer()

        self.set_status("MENYAMBUNGKAN...", color=(0, 0.9, 1, 1), mode_info="MESIN // YT-DLP")
        self.btn_play_pause.set_icon('pause')
        self.update_lockscreen_widget('playing', self.current_title)

        threading.Thread(target=self._bg_extract_audio, args=(self.active_url, self.current_title, self.preview_task_id), daemon=True).start()

    def _bg_extract_audio(self, youtube_url, display_title, task_id):
        if not self.check_internet():
            def _fail_net(dt):
                self.is_playing = False
                self._resume_pos = 0
                self.set_status("GALAT JARINGAN:\nTIDAK ADA INTERNET", color=(1, 0.3, 0.3, 1), mode_info="GALAT // OFFLINE")
                self._stop_visualizer()
                self.reset_preview_buttons()
                if self._current_ready_callback:
                    self._current_ready_callback()
                    self._current_ready_callback = None
            Clock.schedule_once(_fail_net)
            return

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'noplaylist': True, 'quiet': True, 'no_warnings': True,
            'skip_download': True, 'socket_timeout': 15, 'nocheckcertificate': True,
            'extractor_args': {'youtube': {'client': ['android', 'ios', 'tv']}},
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/112.0.0.0 Mobile'}
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                if not info: raise Exception("Data kosong")
                audio_url = info.get('url')

            if self.preview_task_id != task_id: return

            Clock.schedule_once(lambda dt: self._main_thread_prepare_audio(audio_url, display_title, task_id), 0)

        except Exception:
            def _fail_ext(dt):
                if self.preview_task_id != task_id: return
                self.is_playing = False
                self._resume_pos = 0
                self.set_status("GALAT: GAGAL EKSTRAK\nCOBA LAGU LAIN", color=(1, 0.3, 0.3, 1), mode_info="GALAT // GAGAL")
                self._stop_visualizer()
                self.reset_preview_buttons()
                if self._current_ready_callback:
                    self._current_ready_callback()
                    self._current_ready_callback = None
                if self.current_index != -1:
                    self.play_next()
            Clock.schedule_once(_fail_ext)

    def _main_thread_prepare_audio(self, audio_url, display_title, task_id):
        if self.preview_task_id != task_id: return

        if IS_ANDROID and self.player:
            self.set_status("MEMUAT BUFFER...", color=(0, 0.9, 1, 1), mode_info="MEMUAT BUFFER")
            try:
                self.player.reset()
                self.player.setDataSource(audio_url)
                if self.USE_ASYNC_LISTENER:
                    self.player.prepareAsync()
                else:
                    self.player.prepare()
                    self._on_prepared_callback()
            except Exception as e:
                self._handle_player_error()

    def play_next(self, instance=None):
        if not self.playlist: return
        self._retry_count = 0
        self._resume_pos = 0
        next_idx = self.current_index + 1
        if next_idx >= len(self.playlist): next_idx = 0
        item = self.playlist[next_idx]
        self.play_from_playlist(item['url'], item['title'], next_idx)

    def stop_audio(self, instance=None):
        if IS_ANDROID and self.player:
            try:
                if self.player.isPlaying() or self.is_paused:
                    self.player.stop()
            except: pass
        self.media_has_started = False
        self.is_playing = False
        self.is_paused = False
        self._paused_by_focus = False
        self._retry_count = 0
        self._resume_pos = 0
        self._stall_count = 0
        self._last_pos = -1

        self.current_index = -1
        self.active_url = None
        self.current_title = "SIAGA SISTEM"

        self._abandon_focus()
        self._stop_visualizer()
        self.btn_play_pause.set_icon('play')
        self.update_lockscreen_widget('stopped', self.current_title)
        self.set_status("", color=(0.4, 0.6, 0.8, 1), mode_info="STATUS: SIAGA")

        self.refresh_playlist_ui()
        self.reset_preview_buttons()

    def load_playlist_data(self):
        if os.path.exists(PLAYLIST_FILE):
            try:
                with open(PLAYLIST_FILE, 'r') as f: return json.load(f)
            except: pass
        return []

    def save_playlist_data(self):
        try:
            with open(PLAYLIST_FILE, 'w') as f: json.dump(self.playlist, f)
        except: pass

    # --- IN-APP YOUTUBE SEARCH PICKER ---
    def open_add_popup(self, instance):
        popup_root = FloatLayout()

        content_box = BoxLayout(
            orientation='vertical', spacing=dp(12), padding=dp(10),
            size_hint=(1, 1), pos_hint={'x': 0, 'y': 0}
        )

        search_box = BoxLayout(orientation='horizontal', spacing=dp(8), size_hint_y=None, height=dp(45))
        search_input = TextInput(
            hint_text="Cari lagu di YouTube...", multiline=False, font_size='14sp',
            background_active='', background_normal='', background_color=(0.1, 0.12, 0.18, 1),
            foreground_color=(1, 1, 1, 1), hint_text_color=(0.4, 0.5, 0.6, 1),
            padding=[dp(12), dp(12), dp(12), dp(12)]
        )
        btn_search = CyberButton(text="CARI", size_hint_x=None, width=dp(70), bg_color=(0.2, 0.4, 0.8, 1), border_color=(0.3, 0.6, 1, 0.8))
        search_box.add_widget(search_input)
        search_box.add_widget(btn_search)
        content_box.add_widget(search_box)

        results_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.results_container = BoxLayout(orientation='vertical', spacing=dp(6), size_hint_y=None)
        self.results_container.bind(minimum_height=self.results_container.setter('height'))

        placeholder_lbl = Label(
            text="Gunakan bilah pencarian di atas untuk menemukan lagu.",
            color=(0.4, 0.5, 0.6, 1), font_size='12sp', size_hint_y=None, height=dp(50),
            halign='center', valign='middle'
        )
        placeholder_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
        self.results_container.add_widget(placeholder_lbl)

        results_scroll.add_widget(self.results_container)
        content_box.add_widget(results_scroll)

        self.search_status = Label(
            text="Ketik judul lagu dan tekan CARI",
            font_size='12sp', color=(0.6, 0.7, 0.8, 1), size_hint_y=None, height=dp(25),
            halign='center', valign='middle'
        )
        self.search_status.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
        content_box.add_widget(self.search_status)

        btn_cancel = CyberButton(text="TUTUP", size_hint_y=None, height=dp(45), bg_color=(0.4, 0.1, 0.15, 1), border_color=(0.8, 0.2, 0.3, 0.8))
        content_box.add_widget(btn_cancel)

        popup_root.add_widget(content_box)

        popup = Popup(
            title='PENCARI YOUTUBE', title_color=(0, 0.95, 1, 1),
            content=popup_root, size_hint=(0.95, 0.8),
            background_color=(0.05, 0.06, 0.08, 1), separator_color=(0, 0.8, 1, 0.8)
        )

        popup.bind(on_dismiss=lambda inst: self.reset_preview_buttons())

        def perform_search(query):
            try:
                ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch5:{query}", download=False)

                entries = info.get('entries', [])
                Clock.schedule_once(lambda dt: populate_results(entries))
            except Exception:
                Clock.schedule_once(lambda dt: update_status("Gagal mencari data! Periksa koneksi.", (1, 0.3, 0.3, 1)))

        def update_status(text, color):
            self.search_status.text = text
            self.search_status.color = color

        def cancel_preview_task(task_id, overlay_instance):
            self.preview_task_id += 1
            overlay_instance.stop()
            if overlay_instance in popup_root.children:
                popup_root.remove_widget(overlay_instance)
            self.stop_audio()
            update_status("Pratinjau dibatalkan.", (1, 0.5, 0.2, 1))

        def execute_preview(url, title, btn_instance):
            if btn_instance.icon_type == 'stop':
                self.stop_audio()
                return

            self.stop_audio()
            btn_instance.set_mode('stop')

            self.preview_task_id += 1
            current_task = self.preview_task_id

            overlay = CyberLoadingOverlay(cancel_cb=lambda: cancel_preview_task(current_task, overlay))
            popup_root.add_widget(overlay)

            def remove_overlay():
                overlay.stop()
                if overlay in popup_root.children:
                    popup_root.remove_widget(overlay)

            self.start_stream_thread(
                custom_title=f"[PRATINJAU] {title}",
                custom_url=url,
                index=-1,
                on_ready_callback=remove_overlay,
                task_id=current_task
            )

        def populate_results(entries):
            self.results_container.clear_widgets()
            if not entries:
                update_status("Tidak ada hasil ditemukan.", (1, 0.8, 0.2, 1))
                return

            update_status("Pilih lagu untuk disimpan atau diputar:", (0.2, 1, 0.4, 1))

            for entry in entries:
                vid_id = entry.get('id')
                vid_title = entry.get('title', 'Judul Tidak Diketahui')
                vid_url = f"https://www.youtube.com/watch?v={vid_id}"

                thumbnails = entry.get('thumbnails', [])
                thumb_url = thumbnails[0]['url'] if thumbnails else ""
                channel_name = entry.get('channel', 'Saluran Tidak Diketahui')

                item_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(70), spacing=dp(10), padding=dp(5))

                if thumb_url:
                    img = AsyncImage(source=thumb_url, size_hint_x=None, width=dp(90), allow_stretch=True, keep_ratio=True)
                    item_box.add_widget(img)

                text_box = BoxLayout(orientation='vertical', spacing=dp(2))
                lbl_title = Label(text=vid_title, font_size='13sp', color=(1, 1, 1, 1), halign="left", valign="middle", shorten=True, shorten_from='right')
                lbl_title.bind(size=lbl_title.setter('text_size'))

                lbl_channel = Label(text=channel_name, font_size='10sp', color=(0.5, 0.6, 0.7, 1), halign="left", valign="top")
                lbl_channel.bind(size=lbl_channel.setter('text_size'))

                text_box.add_widget(lbl_title)
                text_box.add_widget(lbl_channel)
                item_box.add_widget(text_box)

                btn_box = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(75), spacing=dp(6))

                btn_play = CyberIconTextButton(text="PUTAR", icon_type='play')
                btn_play.bind(on_press=lambda inst, u=vid_url, t=vid_title: execute_preview(u, t, inst))

                btn_save = CyberButton(
                    text="+ SIMPAN", font_size='11sp',
                    bg_color=(0.1, 0.5, 0.2, 1), border_color=(0.3, 0.9, 0.4, 0.9)
                )
                btn_save.bind(on_press=lambda inst, u=vid_url, t=vid_title: auto_save_and_close(u, t))

                btn_box.add_widget(btn_play)
                btn_box.add_widget(btn_save)

                item_box.add_widget(btn_box)
                self.results_container.add_widget(item_box)

        def auto_save_and_close(url, title):
            for item in self.playlist:
                if item['url'] == url:
                    self.set_status("LAGU SUDAH ADA DI DAFTAR", color=(1, 0.7, 0.2, 1), mode_info="DAFTAR // ADA")
                    popup.dismiss()
                    return

            self.playlist.append({"title": title, "url": url})
            self.save_playlist_data()
            self.refresh_playlist_ui()
            self.set_status(f"DISIMPAN:\n{title[:35]}", color=(0.2, 1.0, 0.4, 1), mode_info="DAFTAR // DISIMPAN")
            popup.dismiss()

        def on_search_click(inst):
            query = search_input.text.strip()
            if not query:
                return
            update_status("Mencari ke YouTube...", (0, 0.95, 1, 1))
            self.results_container.clear_widgets()
            threading.Thread(target=perform_search, args=(query,), daemon=True).start()

        btn_search.bind(on_press=on_search_click)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()

    def confirm_remove_popup(self, item_index, item_title):
        content_box = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(10))
        lbl_confirm = Label(
            text=f"Hapus dari pustaka?\n\n{item_title}",
            font_size='14sp', color=(1, 1, 1, 1), halign="center", valign="middle"
        )
        content_box.add_widget(lbl_confirm)

        btn_box = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(45))
        btn_yes = CyberButton(text="HAPUS", bg_color=(0.55, 0.1, 0.15, 1), border_color=(1, 0.2, 0.3, 0.8), font_size='14sp')
        btn_no = CyberButton(text="BATAL", bg_color=(0.15, 0.15, 0.25, 1), border_color=(0.4, 0.4, 0.5, 0.5), font_size='14sp')

        btn_box.add_widget(btn_yes)
        btn_box.add_widget(btn_no)
        content_box.add_widget(btn_box)

        popup = Popup(
            title='KONFIRMASI', title_color=(1, 0.2, 0.3, 1), content=content_box,
            size_hint=(0.85, None), height=dp(200), background_color=(0.05, 0.06, 0.08, 1), separator_color=(1, 0.2, 0.3, 0.8)
        )

        def do_delete(inst):
            self.remove_from_playlist(item_index)
            popup.dismiss()

        btn_yes.bind(on_press=do_delete)
        btn_no.bind(on_press=popup.dismiss)
        popup.open()

    def remove_from_playlist(self, item_index):
        if 0 <= item_index < len(self.playlist):
            self.playlist.pop(item_index)
            self.save_playlist_data()
            if item_index < self.current_index: self.current_index -= 1
            elif item_index == self.current_index: self.current_index = -1
            self.refresh_playlist_ui()

    def play_from_playlist(self, url, custom_title, index):
        self._retry_count = 0
        self._resume_pos = 0
        self.start_stream_thread(custom_title=custom_title, custom_url=url, index=index)

    def refresh_playlist_ui(self):
        self.playlist_container.clear_widgets()
        if not self.playlist:
            empty_lbl = Label(text="Daftar putar kosong. Cari lagu di atas.", font_size='13sp', color=(0.4, 0.5, 0.6, 1), size_hint_y=None, height=dp(40), halign='center')
            empty_lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))
            self.playlist_container.add_widget(empty_lbl)
            return

        active_widgets = []
        inactive_widgets = []

        for idx, item in enumerate(self.playlist):
            is_active = (idx == self.current_index)
            list_item = PlaylistItem(
                idx=idx, title=item['title'], url=item['url'],
                play_cb=self.play_from_playlist,
                del_cb=lambda i=idx, t=item['title']: self.confirm_remove_popup(i, t),
                is_active=is_active
            )
            if is_active: active_widgets.append(list_item)
            else: inactive_widgets.append(list_item)

        for widget in active_widgets: self.playlist_container.add_widget(widget)
        for widget in inactive_widgets: self.playlist_container.add_widget(widget)

    def on_stop(self):
        self._stop_visualizer()
        self._abandon_focus()
        if IS_ANDROID and self.player:
            try: self.player.release()
            except Exception: pass
        if hasattr(self, 'media_session'):
            try:
                self.media_session.setActive(False)
                self.media_session.release()
            except Exception: pass
        if self.eq_instance:
            try: self.eq_instance.release()
            except Exception: pass

if __name__ == '__main__':
    WinampCyberPlayer().run()
