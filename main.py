import threading
import socket
import json
import os
import random
import colorsys
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.popup import Popup
from kivy.uix.behaviors import ButtonBehavior
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle, Line
import yt_dlp

# --- DETEKSI SISTEM OPERASI ANDROID NATIVE & AUDIOFX ---
IS_ANDROID = False
try:
    from jnius import autoclass
    MediaPlayer = autoclass('android.media.MediaPlayer')
    AudioManager = autoclass('android.media.AudioManager')
    Equalizer = autoclass('android.media.audiofx.Equalizer')
    IS_ANDROID = True
except ImportError:
    pass

PLAYLIST_FILE = "playlist_yt.json"
EQ_CONFIG_FILE = "eq_yt.json"

# --- 1. KOMPONEN TOMBOL GAYA SPOTIFY (PILL / ROUNDED) ---
class SpotifyButton(ButtonBehavior, Label):
    def __init__(self, bg_color=(0.11, 0.72, 0.33, 1), text_color=(1,1,1,1), **kwargs):
        super(SpotifyButton, self).__init__(**kwargs)
        self.bg_color = bg_color
        self.color = text_color
        self.bold = True
        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down':
                Color(self.bg_color[0]*0.8, self.bg_color[1]*0.8, self.bg_color[2]*0.8, self.bg_color[3])
            else:
                Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[self.height / 2])

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
            if self.state == 'down':
                Color(min(1.0, self.bg_color[0] * 1.5), min(1.0, self.bg_color[1] * 1.5), min(1.0, self.bg_color[2] * 1.5), 1)
            else:
                Color(*self.bg_color)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)]) 
            Color(*self.border_color)
            Line(rounded_rectangle=(self.pos[0], self.pos[1], self.size[0], self.size[1], dp(8)), width=dp(1.2))

# --- 2. IKON DELETE CUSTOM (DIGAMBAR MENGGUNAKAN CANVAS) ---
class DeleteIcon(ButtonBehavior, BoxLayout):
    def __init__(self, **kwargs):
        super(DeleteIcon, self).__init__(**kwargs)
        self.size_hint = (None, None)
        self.size = (dp(35), dp(35))
        self.pos_hint = {'center_y': 0.5}
        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down':
                Color(1, 0.2, 0.3, 0.8) # Nyala merah terang saat ditekan
            else:
                Color(0.2, 0.1, 0.15, 0.8) # Background merah gelap
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            
            # Menggambar ikon silang (X) yang keren dan anti-error/tofu
            Color(1, 0.2, 0.4, 1)
            margin = dp(10)
            Line(points=[self.x + margin, self.y + margin, self.right - margin, self.top - margin], width=dp(1.8), cap='round')
            Line(points=[self.right - margin, self.y + margin, self.x + margin, self.top - margin], width=dp(1.8), cap='round')


# --- 3. ITEM PLAYLIST GAYA SPOTIFY ---
class PlaylistItem(ButtonBehavior, BoxLayout):
    def __init__(self, idx, title, url, play_cb, del_cb, **kwargs):
        super(PlaylistItem, self).__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(65)
        self.padding = [dp(12), dp(10), dp(10), dp(10)]
        self.spacing = dp(10)
        
        self.bind(pos=self.update_canvas, size=self.update_canvas, state=self.update_canvas)

        text_box = BoxLayout(orientation='vertical', spacing=dp(2))
        self.lbl_title = Label(text=title, font_size='15sp', color=(0.95, 0.95, 0.95, 1), bold=True, halign="left", valign="bottom", shorten=True, shorten_from='right')
        self.lbl_title.bind(size=self.lbl_title.setter('text_size'))
        
        self.lbl_sub = Label(text="YouTube Audio Stream", font_size='11sp', color=(0.5, 0.6, 0.7, 1), halign="left", valign="top")
        self.lbl_sub.bind(size=self.lbl_sub.setter('text_size'))
        
        text_box.add_widget(self.lbl_title)
        text_box.add_widget(self.lbl_sub)

        # Menggunakan tombol delete custom
        btn_del = DeleteIcon()
        btn_del.bind(on_press=lambda inst: del_cb())
        
        self.add_widget(text_box)
        self.add_widget(btn_del)
        
        self.idx = idx
        self.url = url
        self.title = title
        self.play_cb = play_cb

    def update_canvas(self, *args):
        self.canvas.before.clear()
        with self.canvas.before:
            if self.state == 'down':
                Color(0.15, 0.16, 0.2, 1) 
            else:
                Color(0, 0, 0, 0)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])

    def on_release(self):
        self.play_cb(self.url, self.title, self.idx)

# --- 4. SPEKTRUM AUDIO GRAFIS ---
class GraphicSpectrum(BoxLayout):
    def __init__(self, **kwargs):
        super(GraphicSpectrum, self).__init__(**kwargs)
        self.size_hint_y = None
        self.height = dp(45)
        self.bars = 22
        self.heights = [4.0] * self.bars
        self.bind(pos=self.draw_bars, size=self.draw_bars)

    def set_levels(self, new_heights):
        self.heights = new_heights
        self.draw_bars()

    def draw_bars(self, *args):
        self.canvas.clear()
        total_w = self.width
        gap = dp(4)
        bar_w = max(dp(2), (total_w - (self.bars + 1) * gap) / self.bars)
        
        with self.canvas:
            for i in range(self.bars):
                bx = self.x + gap + i * (bar_w + gap)
                bh = max(dp(4), (self.heights[i] / 100.0) * (self.height - dp(4)))
                by = self.y + dp(2)
                
                ratio = i / self.bars
                r = 1.0 - (ratio * 0.8)
                g = 0.1 + (ratio * 0.9)
                b = 0.4 + (ratio * 0.6)
                Color(r, g, b, 0.95)
                RoundedRectangle(pos=(bx, by), size=(bar_w, bh), radius=[dp(2)])


class WinampCyberPlayer(App):
    def build(self):
        Window.clearcolor = (0.05, 0.05, 0.07, 1) 

        if IS_ANDROID:
            self.player = MediaPlayer()
            self.player.setAudioStreamType(AudioManager.STREAM_MUSIC)
        else:
            self.player = None
            
        self.is_paused = False
        self.is_playing = False
        self.media_has_started = False
        
        self.current_title = "SYSTEM STANDBY"
        self.active_url = None 
        self.current_index = -1  
        
        self.eq_event = None
        self.title_hue = 0.0
        
        self.playlist = self.load_playlist_data()
        self.init_equalizer()

        # ROOT LAYOUT
        main_layout = BoxLayout(orientation='vertical', padding=[dp(16), dp(16), dp(16), dp(16)], spacing=dp(12))

        # HEADER (Judul Animasi Berjalan)
        header_box = BoxLayout(size_hint_y=None, height=dp(30))
        self.title_label = Label(text="YT AUDIO PLAYER", font_size='20sp', color=(1, 0.1, 0.3, 1), bold=True, halign="left")
        self.title_label.bind(size=self.title_label.setter('text_size'))
        header_box.add_widget(self.title_label)
        main_layout.add_widget(header_box)
        
        Clock.schedule_interval(self._animate_title_color, 0.05)

        # NOW PLAYING PANEL LCD
        self.lcd_container = BoxLayout(orientation='vertical', padding=[dp(14), dp(14), dp(14), dp(14)], spacing=dp(8), size_hint_y=None, height=dp(135))
        self.lcd_container.bind(pos=self._update_lcd_canvas, size=self._update_lcd_canvas)

        self.lcd_mode = Label(text="READY TO STREAM", font_size='11sp', color=(1, 0.4, 0.6, 0.8), size_hint_y=None, height=dp(16), halign="left")
        self.lcd_mode.bind(size=self.lcd_mode.setter('text_size'))

        self.status_label = Label(
            text="SELECT SONG FROM PLAYLIST", 
            font_size='14sp', color=(0, 0.95, 1, 1), bold=True, halign="center", valign="middle"
        )
        self.status_label.bind(size=self.status_label.setter('text_size'))

        self.spectrum = GraphicSpectrum()

        self.lcd_container.add_widget(self.lcd_mode)
        self.lcd_container.add_widget(self.status_label)
        self.lcd_container.add_widget(self.spectrum)
        main_layout.add_widget(self.lcd_container)

        # KONTROL MEDIA (GAYA SPOTIFY: STOP - PLAY/PAUSE - NEXT)
        control_grid = BoxLayout(orientation='horizontal', spacing=dp(15), padding=[dp(20), 0, dp(20), 0], size_hint_y=None, height=dp(55))
        
        self.btn_stop = SpotifyButton(text="STOP", font_size='13sp', bg_color=(0.2, 0.2, 0.25, 1), text_color=(0.8, 0.8, 0.8, 1))
        self.btn_stop.bind(on_press=self.stop_audio)
        
        self.btn_play_pause = SpotifyButton(text="PLAY", font_size='16sp', bg_color=(0.11, 0.72, 0.33, 1), text_color=(0, 0, 0, 1), size_hint_x=1.3)
        self.btn_play_pause.bind(on_press=self.toggle_play_pause)
        
        self.btn_next = SpotifyButton(text="NEXT", font_size='13sp', bg_color=(0.2, 0.2, 0.25, 1), text_color=(0.8, 0.8, 0.8, 1))
        self.btn_next.bind(on_press=self.play_next)
        
        control_grid.add_widget(self.btn_stop)
        control_grid.add_widget(self.btn_play_pause)
        control_grid.add_widget(self.btn_next)
        main_layout.add_widget(control_grid)

        # TOMBOL TAMBAH PLAYLIST
        btn_add_link = CyberButton(
            text="+ ADD YOUTUBE LINK TO PLAYLIST", 
            size_hint_y=None, height=dp(40), 
            bg_color=(0.1, 0.15, 0.25, 1), border_color=(0.3, 0.4, 0.6, 0.5), font_size='13sp', color=(0.7, 0.8, 0.9, 1)
        )
        btn_add_link.bind(on_press=self.open_add_popup)
        main_layout.add_widget(btn_add_link)

        # EQUALIZER PANEL
        self.eq_container = BoxLayout(orientation='vertical', padding=[dp(8), dp(8), dp(8), dp(8)], spacing=dp(4), size_hint_y=None, height=dp(150))
        self.eq_container.bind(pos=self._update_eq_canvas, size=self._update_eq_canvas)
        
        eq_header = Label(text="DSP EQUALIZER", font_size='11sp', color=(0.8, 0.8, 0.8, 1), bold=True, size_hint_y=None, height=dp(18))
        self.eq_container.add_widget(eq_header)
        
        eq_sliders = BoxLayout(orientation='horizontal', spacing=dp(6))
        self.eq_colors = [
            [1.0, 0.2, 0.4, 1], # Sub Bass
            [0.8, 0.2, 1.0, 1], # Bass
            [0.3, 0.5, 1.0, 1], # Mid
            [0.0, 0.9, 1.0, 1], # Presence
            [0.2, 1.0, 0.4, 1], # Brilliance
        ]

        for i in range(self.eq_bands):
            band_box = BoxLayout(orientation='vertical', spacing=dp(0))
            freq_hz = self.eq_freqs[i] / 1000.0
            freq_str = f"{freq_hz/1000:.1f}k" if freq_hz >= 1000 else f"{int(freq_hz)}"
            lbl_freq = Label(text=freq_str, font_size='10sp', color=(0.6, 0.7, 0.8, 1), size_hint_y=None, height=dp(15))
            
            db_val = self.eq_levels[i] / 100.0
            lbl_db = Label(text=f"{db_val:+.0f}dB", font_size='10sp', color=self.eq_colors[i], bold=True, size_hint_y=None, height=dp(15))
            
            # --- MEMPERKECIL KURSOR LINGKARAN EQUALIZER (cursor_size) ---
            slider = Slider(
                orientation='vertical', min=self.eq_range[0], max=self.eq_range[1],
                value=self.eq_levels[i], step=100, size_hint_y=1,
                value_track=True, value_track_color=self.eq_colors[i],
                cursor_size=(dp(16), dp(16)) # Diperkecil menjadi setengah dari default
            )
            slider.bind(value=lambda instance, val, idx=i, lbl=lbl_db: self.on_eq_change(idx, val, lbl))
            
            band_box.add_widget(lbl_db)
            band_box.add_widget(slider)
            band_box.add_widget(lbl_freq)
            eq_sliders.add_widget(band_box)
            
        self.eq_container.add_widget(eq_sliders)
        main_layout.add_widget(self.eq_container)

        # PLAYLIST AREA HEADER
        pl_header = Label(text="YOUR LIBRARY :", font_size='13sp', color=(0.6, 0.7, 0.8, 1), bold=True, size_hint_y=None, height=dp(20), halign="left")
        pl_header.bind(size=pl_header.setter('text_size'))
        main_layout.add_widget(pl_header)

        # PLAYLIST SCROLLVIEW
        playlist_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.playlist_container = BoxLayout(orientation='vertical', spacing=dp(4), size_hint_y=None)
        self.playlist_container.bind(minimum_height=self.playlist_container.setter('height'))
        
        playlist_scroll.add_widget(self.playlist_container)
        main_layout.add_widget(playlist_scroll)

        self.refresh_playlist_ui()
        
        # Pengecekan otomatis jika lagu habis diputar
        Clock.schedule_interval(self._check_playback_finished, 1.0)
        
        return main_layout

    def _animate_title_color(self, dt):
        self.title_hue += 0.01
        if self.title_hue > 1.0:
            self.title_hue = 0.0
        r, g, b = colorsys.hsv_to_rgb(self.title_hue, 0.8, 1.0)
        self.title_label.color = (r, g, b, 1)

    def _check_playback_finished(self, dt):
        if not IS_ANDROID or not self.player: return
        
        if self.is_playing and not self.is_paused and self.media_has_started:
            if not self.player.isPlaying():
                self.media_has_started = False
                self.is_playing = False
                self._stop_visualizer()
                self.btn_play_pause.text = "PLAY"
                Clock.schedule_once(lambda dt: self.play_next(), 0.5)

    # --- EQUALIZER LOGIC ---
    def init_equalizer(self):
        self.eq_bands = 5
        self.eq_range = [-1500, 1500] 
        self.eq_freqs = [60000, 230000, 910000, 3600000, 14000000] 
        self.eq_levels = [0, 0, 0, 0, 0]
        self.eq_instance = None

        if IS_ANDROID and self.player:
            try:
                self.eq_instance = Equalizer(0, self.player.getAudioSessionId())
                self.eq_instance.setEnabled(True)
                self.eq_bands = self.eq_instance.getNumberOfBands()
                self.eq_range = self.eq_instance.getBandLevelRange() 
                self.eq_freqs = [self.eq_instance.getCenterFreq(i) for i in range(self.eq_bands)]
                self.eq_levels = [0] * self.eq_bands
            except Exception as e:
                pass

        if os.path.exists(EQ_CONFIG_FILE):
            try:
                with open(EQ_CONFIG_FILE, 'r') as f:
                    saved_eq = json.load(f)
                if len(saved_eq) == self.eq_bands:
                    self.eq_levels = saved_eq
            except: pass

        if self.eq_instance:
            for i in range(self.eq_bands):
                try: self.eq_instance.setBandLevel(i, self.eq_levels[i])
                except: pass

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

    # --- UI UPDATE & EFFECTS ---
    def _update_eq_canvas(self, *args):
        self.eq_container.canvas.before.clear()
        with self.eq_container.canvas.before:
            Color(0.08, 0.08, 0.1, 1)
            RoundedRectangle(pos=self.eq_container.pos, size=self.eq_container.size, radius=[dp(6)])
            Color(0.4, 0.4, 0.5, 0.5) 
            Line(rounded_rectangle=(self.eq_container.x, self.eq_container.y, self.eq_container.width, self.eq_container.height, dp(6)), width=dp(0.8))

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
        else:
            new_levels = [3.0] * self.spectrum.bars
        self.spectrum.set_levels(new_levels)

    def _start_visualizer(self):
        if not self.eq_event:
            self.eq_event = Clock.schedule_interval(self._update_spectrum_tick, 0.1)

    def _stop_visualizer(self):
        if self.eq_event:
            self.eq_event.cancel()
            self.eq_event = None
        self.spectrum.set_levels([3.0] * self.spectrum.bars)

    def set_status(self, text, color=(0.1, 1.0, 0.3, 1), mode_info="STATUS: ACTIVE"):
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

    # --- PLAYBACK & YT-DLP CORE ---
    def toggle_play_pause(self, instance=None):
        if not self.active_url:
            if self.playlist:
                self.play_next(None)
            else:
                self.set_status("PLEASE ADD SONG\nTO PLAYLIST", color=(1, 0.4, 0.4, 1), mode_info="ERR // NO_URL")
            return

        if self.is_playing and not self.is_paused:
            if IS_ANDROID and self.player and self.player.isPlaying():
                self.player.pause()
            self.is_paused = True
            self.is_playing = False
            self.btn_play_pause.text = "PLAY"
            self.set_status("PLAYBACK PAUSED", color=(1, 0.7, 0.1, 1), mode_info="STATE: PAUSED")
        
        elif self.is_paused:
            if IS_ANDROID and self.player: 
                self.player.start()
            self.is_paused = False
            self.is_playing = True
            self.btn_play_pause.text = "PAUSE"
            self.set_status(f"RESUMED:\n{self.current_title[:35]}", color=(0, 1.0, 0.8, 1), mode_info="STATE: PLAYING")
            self._start_visualizer()
            
        else:
            self.start_stream_thread()

    def start_stream_thread(self, custom_title=None, custom_url=None, index=-1):
        if custom_url:
            self.active_url = custom_url
            self.current_title = custom_title if custom_title else "LIVE STREAM"
            self.current_index = index

        if not self.active_url:
            return

        self.media_has_started = False
        self.set_status("CONNECTING...", color=(0, 0.9, 1, 1), mode_info="ENGINE // YT-DLP")
        self.btn_play_pause.text = "PAUSE"
        
        threading.Thread(target=self.extract_and_play, args=(self.active_url, self.current_title), daemon=True).start()

    def extract_and_play(self, youtube_url, display_title):
        if not self.check_internet():
            self.set_status("NETWORK ERROR:\nNO INTERNET", color=(1, 0.3, 0.3, 1), mode_info="ERR // OFFLINE")
            Clock.schedule_once(lambda dt: self._stop_visualizer())
            Clock.schedule_once(lambda dt: setattr(self.btn_play_pause, 'text', 'PLAY'))
            return

        self.set_status("RESOLVING AUDIO...\nPLEASE WAIT", color=(1, 0.8, 0.2, 1), mode_info="FETCHING MEDIA")

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
                if not info: raise Exception("No data")

                audio_url = info.get('url')

                if IS_ANDROID and self.player:
                    self.set_status("BUFFERING...", color=(0, 0.9, 1, 1), mode_info="BUFFERING")
                    self.player.reset()
                    self.player.setDataSource(audio_url)
                    self.player.prepare()
                    self.player.start()
                    self.media_has_started = True

                self.is_playing = True
                self.is_paused = False
                Clock.schedule_once(lambda dt: self._start_visualizer())
                self.set_status(f"{display_title[:45]}", color=(0, 1.0, 0.8, 1), mode_info="PLAYING // HI-FI")

        except Exception as e:
            self.set_status("ERROR: EXTRACT FAILED\nTRY ANOTHER SONG", color=(1, 0.3, 0.3, 1), mode_info="ERR // FAILED")
            Clock.schedule_once(lambda dt: self._stop_visualizer())
            Clock.schedule_once(lambda dt: setattr(self.btn_play_pause, 'text', 'PLAY'))
            Clock.schedule_once(lambda dt: self.play_next(), 3.0)

    def play_next(self, instance=None):
        if not self.playlist:
            return
            
        next_idx = self.current_index + 1
        if next_idx >= len(self.playlist):
            next_idx = 0 
            
        item = self.playlist[next_idx]
        self.play_from_playlist(item['url'], item['title'], next_idx)

    def stop_audio(self, instance=None):
        if IS_ANDROID and self.player:
            if self.player.isPlaying() or self.is_paused:
                self.player.stop()
        self.media_has_started = False
        self.is_playing = False
        self.is_paused = False
        self._stop_visualizer()
        self.btn_play_pause.text = "PLAY"
        self.set_status("STOPPED // IDLE", color=(0.4, 0.6, 0.8, 1), mode_info="STATE: IDLE")

    # --- PLAYLIST MANAGEMENT & POPUP ---
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

    def open_add_popup(self, instance):
        content_box = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(10))
        
        url_input = TextInput(
            hint_text="Paste YouTube URL Here", multiline=False, font_size='14sp', 
            background_active='', background_normal='', background_color=(0.1, 0.12, 0.18, 1),
            foreground_color=(1, 1, 1, 1), hint_text_color=(0.4, 0.5, 0.6, 1),
            padding=[dp(12), dp(12), dp(12), dp(12)], size_hint_y=None, height=dp(45)
        )
        
        name_input = TextInput(
            hint_text="Enter Display Name (e.g. Chill Mix)", multiline=False, font_size='14sp', 
            background_active='', background_normal='', background_color=(0.1, 0.12, 0.18, 1),
            foreground_color=(1, 1, 1, 1), hint_text_color=(0.4, 0.5, 0.6, 1),
            padding=[dp(12), dp(12), dp(12), dp(12)], size_hint_y=None, height=dp(45)
        )
        
        content_box.add_widget(url_input)
        content_box.add_widget(name_input)

        btn_box = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(45))
        btn_save_confirm = CyberButton(text="SAVE", bg_color=(0.08, 0.45, 0.2, 1), border_color=(0.1, 0.8, 0.3, 0.8), font_size='14sp')
        btn_cancel = CyberButton(text="CANCEL", bg_color=(0.4, 0.1, 0.15, 1), border_color=(0.8, 0.2, 0.3, 0.8), font_size='14sp')
        
        btn_box.add_widget(btn_save_confirm)
        btn_box.add_widget(btn_cancel)
        content_box.add_widget(btn_box)

        popup = Popup(
            title='ADD TO LIBRARY',
            title_color=(0, 0.95, 1, 1),
            content=content_box,
            size_hint=(0.9, None), height=dp(230),
            background_color=(0.05, 0.06, 0.08, 1),
            separator_color=(0, 0.8, 1, 0.8)
        )

        def confirm_save(inst):
            url = url_input.text.strip()
            display_name = name_input.text.strip()
            
            if not url:
                self.set_status("ERROR: URL IS EMPTY", color=(1, 0.4, 0.4, 1), mode_info="ERR // NO_URL")
                popup.dismiss()
                return
                
            if not display_name: display_name = "SAVED STREAM"

            for item in self.playlist:
                if item['url'] == url:
                    self.set_status("ALREADY IN PLAYLIST", color=(1, 0.7, 0.2, 1), mode_info="PLAYLIST // EXIST")
                    popup.dismiss()
                    return

            self.playlist.append({"title": display_name, "url": url})
            self.save_playlist_data()
            self.refresh_playlist_ui()
            self.set_status(f"SAVED: {display_name.upper()}", color=(0.2, 1.0, 0.4, 1), mode_info="PLAYLIST // SAVED")
            popup.dismiss()

        btn_save_confirm.bind(on_press=confirm_save)
        btn_cancel.bind(on_press=popup.dismiss)
        popup.open()

    def confirm_remove_popup(self, item_index, item_title):
        content_box = BoxLayout(orientation='vertical', spacing=dp(12), padding=dp(10))
        lbl_confirm = Label(
            text=f"Remove from library?\n\n{item_title}", 
            font_size='14sp', color=(1, 1, 1, 1), halign="center", valign="middle"
        )
        content_box.add_widget(lbl_confirm)

        btn_box = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(45))
        btn_yes = CyberButton(text="REMOVE", bg_color=(0.55, 0.1, 0.15, 1), border_color=(1, 0.2, 0.3, 0.8), font_size='14sp')
        btn_no = CyberButton(text="CANCEL", bg_color=(0.15, 0.15, 0.25, 1), border_color=(0.4, 0.4, 0.5, 0.5), font_size='14sp')
        
        btn_box.add_widget(btn_yes)
        btn_box.add_widget(btn_no)
        content_box.add_widget(btn_box)

        popup = Popup(
            title='CONFIRM', title_color=(1, 0.2, 0.3, 1), content=content_box,
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
            self.refresh_playlist_ui()
            
            if item_index < self.current_index:
                self.current_index -= 1
            elif item_index == self.current_index:
                self.current_index = -1

    def play_from_playlist(self, url, custom_title, index):
        self.start_stream_thread(custom_title=custom_title, custom_url=url, index=index)

    def refresh_playlist_ui(self):
        self.playlist_container.clear_widgets()
        
        if not self.playlist:
            empty_lbl = Label(text="No Playlist Available. Add a link above.", font_size='13sp', color=(0.4, 0.5, 0.6, 1), size_hint_y=None, height=dp(40))
            self.playlist_container.add_widget(empty_lbl)
            return
            
        for idx, item in enumerate(self.playlist):
            list_item = PlaylistItem(
                idx=idx, title=item['title'], url=item['url'],
                play_cb=self.play_from_playlist,
                del_cb=lambda i=idx, t=item['title']: self.confirm_remove_popup(i, t)
            )
            self.playlist_container.add_widget(list_item)

    def on_stop(self):
        self._stop_visualizer()
        if IS_ANDROID and self.player:
            self.player.release()
        if self.eq_instance:
            self.eq_instance.release()

if __name__ == '__main__':
    WinampCyberPlayer().run()
