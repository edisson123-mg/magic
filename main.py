import os
import json
import threading
import time
import requests
from datetime import datetime
from decimal import Decimal, getcontext
getcontext().prec = 28
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.clock import Clock, mainthread
from kivy.graphics import Color, Rectangle
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.utils import platform

# Wake Lock para Android (mantiene el bot vivo)
if platform == 'android':
    from jnius import autoclass
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    Activity = autoclass('android.app.Activity')
    PowerManager = autoclass('android.os.PowerManager')

try:
    from binance.client import Client
    from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
    REAL_CLIENT_AVAILABLE = True
except ImportError:
    REAL_CLIENT_AVAILABLE = False

# ====================== CONSTANTES ======================
CONFIG_FILE = "api_config.json"
ACUMULADO_FILE = "acumulado_mes.json"
POSITIONS_FILE = "posiciones.json"

PUMP_TP_INITIAL = 3.0
PUMP_SL_INITIAL = 5.0
PUMP_TP_STEP = 3.0
TRAILING_SL_PCT = 1.5
RISK_MAX_PERCENT = 1.5
AUTO_SCAN_INTERVAL = 3  # Escanea cada 3 segundos
MAX_CONCURRENT_TRADES = 5

PUMP_PRICE_SPIKE_PCT = 1.2
MIN_PURCHASE_USDT = 5.0
MIN_CURRENT_VALUE_USDT = 5.0

COLOR_BG_DARK = (0.1, 0.1, 0.15, 1)
COLOR_CARD_DARK = (0.15, 0.15, 0.2, 1)
COLOR_ACCENT_NEON = (0.0, 0.8, 0.5, 1)
COLOR_ACCENT_ERROR = (0.9, 0.2, 0.2, 1)
COLOR_TEXT_LIGHT = (0.9, 0.9, 0.9, 1)
COLOR_TEXT_MUTED = (0.6, 0.6, 0.6, 1)
NUM_TRADING_SECTIONS = 10

FONT_SIZE_TITLE = "24sp"
FONT_SIZE_NORMAL = "14sp"
FONT_SIZE_SMALL = "12sp"
FONT_SIZE_ACCENT = "16sp"

# ====================== LOGS ======================
LOG_LINES = []
MAX_LOG_LINES = 1000

def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    full_msg = f"[{timestamp}] {message}"
    print(full_msg)
    LOG_LINES.append(full_msg)
    if len(LOG_LINES) > MAX_LOG_LINES:
        LOG_LINES.pop(0)

# ====================== UTILIDADES ======================
def get_price_usdt(symbol):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}", timeout=8)
        return float(r.json()["price"])
    except:
        return None

def get_real_usdt_balance_total():
    keys = load_api_keys()
    if not REAL_CLIENT_AVAILABLE or not keys.get("api"):
        return 0.0
    try:
        client = Client(keys["api"], keys["secret"])
        bal = client.get_asset_balance('USDT')
        return float(bal['free']) + float(bal['locked'])
    except:
        return 0.0

class RealBinanceClientWrapper:
    def _init_(self, api_key, api_secret):
        self.use_real = REAL_CLIENT_AVAILABLE and api_key and api_key != "SIM_API"
        if self.use_real:
            try:
                self.client = Client(api_key, api_secret)
                self.client.ping()
            except:
                self.use_real = False
                log("Error conectando Binance - modo sin API real")

    def create_market_buy_order(self, symbol, quantity):
        if self.use_real:
            try:
                return self.client.create_order(symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=quantity)
            except Exception as e:
                log(f"Error compra: {e}")
                return None
        return None

    def create_market_sell_order(self, symbol, quantity):
        if self.use_real:
            try:
                return self.client.create_order(symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=quantity)
            except Exception as e:
                log(f"Error venta: {e}")
                return None
        return None

    def get_symbol_info(self, symbol):
        if self.use_real:
            try:
                return self.client.get_symbol_info(symbol)
            except:
                return None
        return None

    def get_asset_balance(self, asset):
        if self.use_real:
            try:
                return self.client.get_asset_balance(asset)
            except:
                return None
        return None

    def get_order(self, symbol, order_id):
        if self.use_real:
            try:
                return self.client.get_order(symbol=symbol, orderId=order_id)
            except:
                return None
        return None

    def get_account(self):
        if self.use_real:
            try:
                return self.client.get_account()
            except Exception as e:
                log(f"Error get_account: {e}")
                return None
        return None

def load_api_keys():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"api": "", "secret": ""}

def save_api_keys(api, secret):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"api": api, "secret": secret}, f)

def load_acumulado():
    default = {"acumulado_real": 0.0}
    if os.path.exists(ACUMULADO_FILE):
        try:
            with open(ACUMULADO_FILE) as f:
                return json.load(f)
        except:
            pass
    return default

def save_acumulado(data):
    with open(ACUMULADO_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_positions_from_file():
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"Error leyendo posiciones.json: {e}")
    return []

def save_positions(positions):
    active_data = [
        s.data for s in positions
        if s.data["estado"] == "COMPRADO" and s.data["inversion"] >= MIN_PURCHASE_USDT
    ]
    try:
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(active_data, f, indent=4)
    except Exception as e:
        log(f"Error guardando posiciones: {e}")

def get_all_usdt_pairs():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get("https://api.binance.com/api/v3/ticker/24hr", headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        pairs = [t['symbol'] for t in data if t['symbol'].endswith('USDT') and t.get('status') == 'TRADING']
        log(f"Pares USDT obtenidos: {len(pairs)}")
        return pairs
    except Exception as e:
        log(f"ERROR obteniendo pares: {e}")
        return []

def detect_pump(symbol):
    try:
        klines = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=20", timeout=10).json()
        if len(klines) < 12:
            return False
        lows = [float(k[3]) for k in klines]
        highs = [float(k[2]) for k in klines]
        recent_lows = lows[-11:]
        price_reference = min(recent_lows[:-1]) if recent_lows[:-1] else lows[-1]
        if price_reference <= 0:
            return False
        max_high = max(highs[-11:])
        current_price = get_price_usdt(symbol) or max_high
        effective_high = max(max_high, current_price)
        spike_pct = ((effective_high - price_reference) / price_reference) * 100
        return spike_pct >= PUMP_PRICE_SPIKE_PCT
    except Exception as e:
        log(f"Error detect_pump {symbol}: {e}")
        return False

class TradingInterface(BoxLayout):
    def _init_(self, **kwargs):
        super()._init_(**kwargs)
        self.sections = []
        self.acum = load_acumulado()
        self.keys = load_api_keys()
        self.scanning = False
        self.bot_start_time = None
        self.initial_sl_blacklist = set()
        self.subsequent_sl = {}
        self.scan_event = None
        self.wake_lock = None

        # Wake Lock para mantener vivo
        if platform == 'android':
            try:
                mActivity = PythonActivity.mActivity
                pm = mActivity.getSystemService(Activity.POWER_SERVICE)
                self.wake_lock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "MagicPump::WakeLock")
                self.wake_lock.acquire()
                log("Wake Lock activado - bot 24/7")
            except Exception as e:
                log(f"Error wake lock: {e}")

        self.orientation = "vertical"
        self.spacing = 10
        self.padding = 10

        with self.canvas.before:
            Color(*COLOR_BG_DARK)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_bg, pos=self._update_bg)

        self.add_widget(Label(text="MAGIC PUMP 24/7", font_size=FONT_SIZE_TITLE, size_hint_y=0.1, color=COLOR_ACCENT_NEON, bold=True))

        self.capital_lbl = Label(text="Capital: Cargando...", size_hint_y=0.04, color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        self.add_widget(self.capital_lbl)

        top = BoxLayout(size_hint_y=0.06, spacing=8)
        self.btn_api = Button(text="CONFI. API", background_color=COLOR_CARD_DARK, font_size=FONT_SIZE_NORMAL)
        self.btn_logs = Button(text="LOGS", background_color=COLOR_CARD_DARK, font_size=FONT_SIZE_NORMAL)
        self.btn_api.bind(on_press=self.config_api)
        self.btn_logs.bind(on_press=self.show_logs_popup)
        top.add_widget(self.btn_api)
        top.add_widget(self.btn_logs)
        self.add_widget(top)

        self.btn_manual_buy = Button(text="COMPRAR MANUAL", background_color=(0.5,1,0,1), size_hint_y=0.06, font_size=FONT_SIZE_NORMAL)
        self.btn_manual_buy.bind(on_press=self.manual_buy_popup)
        self.add_widget(self.btn_manual_buy)

        self.status_lbl = Label(text="Bot iniciando...", size_hint_y=0.04, color=COLOR_ACCENT_NEON, font_size=FONT_SIZE_NORMAL)
        self.add_widget(self.status_lbl)

        scroll = ScrollView(size_hint=(1, 0.5))
        cont = BoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        cont.bind(minimum_height=cont.setter('height'))

        for i in range(NUM_TRADING_SECTIONS):
            sec = self.create_section(i)
            self.sections.append(sec)
            cont.add_widget(sec)

        scroll.add_widget(cont)
        self.add_widget(scroll)

        bottom = BoxLayout(size_hint_y=0.14, orientation="vertical", padding=8)
        with bottom.canvas.before:
            Color(*COLOR_CARD_DARK)
            Rectangle(size=bottom.size, pos=bottom.pos)
        bottom.add_widget(Label(text="G/P ACUMULADA REAL", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))
        self.acum_real_lbl = Label(text="$0.00 USDT", color=COLOR_ACCENT_NEON, font_size=FONT_SIZE_ACCENT)
        bottom.add_widget(self.acum_real_lbl)
        self.date_lbl = Label(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL)
        bottom.add_widget(self.date_lbl)
        self.add_widget(bottom)

        self.recover_all_active_positions()

        Clock.schedule_interval(self.update_all, 1)
        Clock.schedule_once(self.update_capital, 1)
        Clock.schedule_once(self.on_start_activation, 2)

        # Evitar cerrar con botón atrás
        Window.bind(on_keyboard=self._on_keyboard)

    def _on_keyboard(self, window, key, *largs):
        if key == 27:  # Botón atrás
            return True  # No cierra la app

    def _update_bg(self, *args):
        self.rect.size = self.size
        self.rect.pos = self.pos

    def create_section(self, idx):
        sec = BoxLayout(orientation="vertical", size_hint_y=None, height=350, spacing=4, padding=8)
        with sec.canvas.before:
            Color(*COLOR_CARD_DARK)
            Rectangle(size=sec.size, pos=sec.pos)

        row1 = BoxLayout(size_hint_y=0.15, spacing=6)
        txt_symbol = TextInput(hint_text="Símbolo", readonly=True, background_color=COLOR_BG_DARK, foreground_color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        btn_vender = Button(text="VENDER AHORA", disabled=True, background_color=COLOR_ACCENT_ERROR, font_size=FONT_SIZE_NORMAL)
        row1.add_widget(txt_symbol)
        row1.add_widget(btn_vender)

        row_inv = BoxLayout(size_hint_y=0.1, spacing=4)
        row_inv.add_widget(Label(text="INVERSIÓN", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))
        row_inv.add_widget(Label(text="CANTIDAD", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))
        row_inv.add_widget(Label(text="P. COMPRA", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))

        row_inv_val = BoxLayout(size_hint_y=0.15, spacing=4)
        lbl_inversion = Label(text="$0.00", color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        lbl_cantidad = Label(text="0.00", color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        inp_entry = TextInput(readonly=True, background_color=COLOR_BG_DARK, foreground_color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        row_inv_val.add_widget(lbl_inversion)
        row_inv_val.add_widget(lbl_cantidad)
        row_inv_val.add_widget(inp_entry)

        row_head = BoxLayout(size_hint_y=0.1, spacing=4)
        for text in ["P. REAL", "P. VENTA", "SL (%)", "TP (%)", "ESTADO"]:
            row_head.add_widget(Label(text=text, color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))

        row_val = BoxLayout(size_hint_y=0.15, spacing=4)
        inp_real = TextInput(readonly=True, background_color=COLOR_BG_DARK, foreground_color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        lbl_p_venta = Label(text="$0.000000", color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        spin_sl = Spinner(text=f"{PUMP_SL_INITIAL:.1f}%", values=[f"{x:.1f}%" for x in range(1,21)], font_size=FONT_SIZE_NORMAL)
        spin_tp = Spinner(text=f"{PUMP_TP_INITIAL:.1f}%", values=[f"{x:.1f}%" for x in range(3,100,3)], font_size=FONT_SIZE_NORMAL)
        lbl_state = Label(text="INACTIVO", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_NORMAL)
        row_val.add_widget(inp_real)
        row_val.add_widget(lbl_p_venta)
        row_val.add_widget(spin_sl)
        row_val.add_widget(spin_tp)
        row_val.add_widget(lbl_state)

        row_prices = BoxLayout(size_hint_y=0.1, spacing=4)
        row_prices.add_widget(Label(text="SL Trailing", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))
        lbl_sl_price = Label(text="$0.000000", color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        row_prices.add_widget(lbl_sl_price)
        row_prices.add_widget(Label(text="TP Precio", color=COLOR_TEXT_MUTED, font_size=FONT_SIZE_SMALL))
        lbl_tp_price = Label(text="$0.000000", color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_NORMAL)
        row_prices.add_widget(lbl_tp_price)

        row_pg = BoxLayout(size_hint_y=0.2)
        row_pg.add_widget(Label(text="G/P (USDT)", color=COLOR_TEXT_MUTED, size_hint_x=0.4, font_size=FONT_SIZE_SMALL))
        inp_pg = TextInput(text="$0.00 USDT", readonly=True, background_color=COLOR_CARD_DARK, foreground_color=COLOR_TEXT_LIGHT, font_size=FONT_SIZE_ACCENT)
        row_pg.add_widget(inp_pg)

        sec.add_widget(row1)
        sec.add_widget(row_inv)
        sec.add_widget(row_inv_val)
        sec.add_widget(row_head)
        sec.add_widget(row_val)
        sec.add_widget(row_prices)
        sec.add_widget(row_pg)

        sec.widgets = {
            "txt_symbol": txt_symbol,
            "inp_real": inp_real,
            "inp_entry": inp_entry,
            "spin_sl": spin_sl,
            "spin_tp": spin_tp,
            "lbl_state": lbl_state,
            "lbl_sl_price": lbl_sl_price,
            "lbl_tp_price": lbl_tp_price,
            "lbl_inversion": lbl_inversion,
            "lbl_cantidad": lbl_cantidad,
            "lbl_p_venta": lbl_p_venta,
            "inp_pg": inp_pg,
            "btn_vender": btn_vender
        }

        sec.data = {
            "estado": "INACTIVO",
            "moneda": None,
            "entry_price": 0.0,
            "cantidad": 0.0,
            "inversion": 0.0,
            "sl_pct": PUMP_SL_INITIAL,
            "tp_pct": PUMP_TP_INITIAL,
            "max_high": 0.0,
            "initial_sl_hit": False,
            "trailing_active": False
        }

        btn_vender.bind(on_press=lambda x, s=sec: self.sell_section(s))
        return sec

    def recover_all_active_positions(self):
        client = RealBinanceClientWrapper(self.keys["api"], self.keys["secret"])
        json_positions = load_positions_from_file()
        json_symbols = {p.get("moneda") for p in json_positions if p.get("moneda")}
        recovered_count = 0

        for pos in json_positions:
            symbol = pos.get("moneda")
            if not symbol or not symbol.endswith("USDT"):
                continue
            asset = symbol.replace("USDT", "")
            bal = client.get_asset_balance(asset)
            if bal and float(bal['free']) > 0:
                price = get_price_usdt(symbol)
                if price and float(bal['free']) * price > MIN_CURRENT_VALUE_USDT:
                    self.assign_position(pos, qty=float(bal['free']), price=price)
                    recovered_count += 1
                    log(f"Recuperada desde JSON: {symbol}")

        if client.use_real:
            account = client.get_account()
            if account:
                for bal_info in account['balances']:
                    asset = bal_info['asset']
                    if asset == "USDT" or float(bal_info['free']) <= 0:
                        continue
                    symbol = asset + "USDT"
                    if symbol in json_symbols:
                        continue
                    price = get_price_usdt(symbol)
                    if price and float(bal_info['free']) * price > MIN_CURRENT_VALUE_USDT:
                        new_pos = {
                            "moneda": symbol,
                            "entry_price": price,
                            "cantidad": float(bal_info['free']),
                            "inversion": float(bal_info['free']) * price,
                            "sl_pct": PUMP_SL_INITIAL,
                            "tp_pct": PUMP_TP_INITIAL,
                            "max_high": price,
                            "initial_sl_hit": False,
                            "trailing_active": False
                        }
                        self.assign_position(new_pos, qty=float(bal_info['free']), price=price)
                        recovered_count += 1
                        log(f"RECUPERADA DE BINANCE: {symbol}")
                        self.alert("RECUPERADO", f"Posición detectada: {symbol}")

        if recovered_count > 0:
            self.alert("RECUPERACIÓN", f"{recovered_count} posiciones recuperadas")
        save_positions(self.sections)

    def assign_position(self, pos_data, qty, price):
        for sec in self.sections:
            if sec.data["estado"] == "INACTIVO":
                entry = pos_data.get("entry_price", price)
                sec.data.update({
                    "estado": "COMPRADO",
                    "moneda": pos_data["moneda"],
                    "entry_price": entry,
                    "cantidad": qty,
                    "inversion": qty * entry,
                    "sl_pct": pos_data.get("sl_pct", PUMP_SL_INITIAL),
                    "tp_pct": pos_data.get("tp_pct", PUMP_TP_INITIAL),
                    "max_high": pos_data.get("max_high", price),
                    "initial_sl_hit": pos_data.get("initial_sl_hit", False),
                    "trailing_active": pos_data.get("trailing_active", False)
                })
                self.update_section_display(sec, price)
                break

    def on_start_activation(self, dt=None):
        self.bot_start_time = time.time()
        log("BOT INICIADO - MODO 24/7")
        self.status_lbl.text = f"Bot activo - Escaneando cada {AUTO_SCAN_INTERVAL}s"
        self.scan_event = Clock.schedule_interval(self.auto_scan, AUTO_SCAN_INTERVAL)

    def update_capital(self, dt=None):
        balance = get_real_usdt_balance_total()
        self.capital_lbl.text = f"Capital: ${balance:,.2f} USDT"

    def update_all(self, dt):
        self.date_lbl.text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.acum_real_lbl.text = f"${self.acum.get('acumulado_real',0):,.2f} USDT"
        threading.Thread(target=self._update_sections_async).start()

    @mainthread
    def _update_sections_async(self):
        active_sections = [s for s in self.sections if s.data["estado"] == "COMPRADO" and s.data["moneda"]]
        if not active_sections:
            return
        symbols = [s.data["moneda"] for s in active_sections]
        prices = {sym: get_price_usdt(sym) for sym in symbols}
        for sec in active_sections:
            price = prices.get(sec.data["moneda"])
            if price:
                self.check_tp_sl(sec, price)
                self.update_section_display(sec, price)
        save_positions(self.sections)

    def _can_scan(self):
        active = sum(1 for s in self.sections if s.data["estado"] == "COMPRADO")
        return active < MAX_CONCURRENT_TRADES

    def auto_scan(self, dt):
        if not self._can_scan() or self.scanning:
            return
        self.scanning = True
        threading.Thread(target=self._do_scan).start()

    def _do_scan(self):
        try:
            symbols = get_all_usdt_pairs()
            self.scan_pumps(symbols)
        finally:
            self.scanning = False

    def scan_pumps(self, symbols):
        if self.bot_start_time is None:
            return
        active = {s.data["moneda"] for s in self.sections if s.data["moneda"]}
        client = RealBinanceClientWrapper(self.keys["api"], self.keys["secret"])
        for symbol in symbols:
            if symbol in active or symbol in self.initial_sl_blacklist:
                continue
            if sum(1 for s in self.sections if s.data["estado"] == "INACTIVO") == 0:
                break
            if symbol in self.subsequent_sl:
                sell_price, sell_time = self.subsequent_sl[symbol]
                current_price = get_price_usdt(symbol)
                if current_price and (current_price - sell_price) / sell_price * 100 < 1.0:
                    continue
                if time.time() - sell_time > 300:
                    del self.subsequent_sl[symbol]
            if detect_pump(symbol):
                self.buy_if_possible(symbol, client)

    def get_adjusted_qty(self, symbol, desired_qty, is_sell=False):
        client_wrapper = RealBinanceClientWrapper(self.keys["api"], self.keys["secret"])
        info = client_wrapper.get_symbol_info(symbol)
        if not info:
            return None
        min_notional = 10.0
        min_qty = 0.0
        step_size = 0.0
        for f in info['filters']:
            if f['filterType'] in ['MIN_NOTIONAL', 'NOTIONAL']:
                min_notional = float(f.get('minNotional', min_notional))
            elif f['filterType'] == 'LOT_SIZE':
                min_qty = float(f['minQty'])
                step_size = float(f['stepSize'])
        price = get_price_usdt(symbol) or 0.000001
        qty_from_notional = Decimal(str(min_notional)) / Decimal(str(price))
        qty = Decimal(str(desired_qty))
        qty = max(qty, qty_from_notional, Decimal(str(min_qty)))
        if step_size > 0:
            step = Decimal(str(step_size))
            if is_sell:
                qty = (qty // step) * step
            else:
                qty = ((qty // step) + (1 if qty % step != 0 else 0)) * step
        return float(qty) if qty > 0 else None

    @mainthread
    def buy_if_possible(self, symbol, client, investment=None, sl_pct=None, tp_pct=None):
        price = get_price_usdt(symbol)
        if not price:
            self.alert("Error", f"Precio no disponible: {symbol}")
            return
        balance = get_real_usdt_balance_total()
        if balance < MIN_PURCHASE_USDT:
            log(f"Compra bloqueada {symbol}: balance insuficiente")
            return
        if investment is not None:
            desired_investment = investment
        else:
            risk = balance * (RISK_MAX_PERCENT / 100)
            desired_investment = risk / (PUMP_SL_INITIAL / 100)
        desired_investment = max(desired_investment, MIN_PURCHASE_USDT)
        desired_qty = desired_investment / price
        qty = self.get_adjusted_qty(symbol, desired_qty)
        if not qty:
            self.alert("Error", f"Cantidad inválida: {symbol}")
            return
        inversion = qty * price
        if inversion > balance:
            self.alert("Error", "Saldo insuficiente")
            return
        order = client.create_market_buy_order(symbol, qty)
        if not order:
            self.alert("Error", f"Compra fallida: {symbol}")
            return
        time.sleep(1)
        order_status = client.get_order(symbol, order['orderId'])
        if not order_status or order_status['status'] != 'FILLED':
            self.alert("Error", f"Orden no completada: {symbol}")
            return
        qty_exec = float(order_status.get('executedQty', qty))
        entry_price = price
        if order_status.get('fills'):
            entry_price = sum(float(f['price']) * float(f['qty']) for f in order_status['fills']) / qty_exec
        inversion = qty_exec * entry_price
        sec = next((s for s in self.sections if s.data["estado"] == "INACTIVO"), None)
        if not sec:
            self.alert("Error", "No hay slots libres")
            return
        sl = sl_pct or PUMP_SL_INITIAL
        tp = tp_pct or PUMP_TP_INITIAL
        sec.data.update({
            "estado": "COMPRADO",
            "moneda": symbol,
            "entry_price": entry_price,
            "cantidad": qty_exec,
            "inversion": inversion,
            "sl_pct": sl,
            "tp_pct": tp,
            "max_high": entry_price,
            "initial_sl_hit": False,
            "trailing_active": False
        })
        save_positions(self.sections)
        self.update_section_display(sec, entry_price)
        self.alert("COMPRA OK", f"{symbol} comprado por ${inversion:.2f} @ {entry_price:.6f}")
        self.update_capital()

    def manual_buy_popup(self, inst):
        content = BoxLayout(orientation="vertical", padding=10, spacing=10)
        symbol_in = TextInput(hint_text="Símbolo ej. BTCUSDT", font_size=FONT_SIZE_NORMAL)
        invest_in = TextInput(hint_text=f"Inversión USDT (mín {MIN_PURCHASE_USDT})", font_size=FONT_SIZE_NORMAL)
        sl_spin = Spinner(text=f"{PUMP_SL_INITIAL:.1f}%", values=[f"{x:.1f}%" for x in range(1,21)])
        tp_spin = Spinner(text=f"{PUMP_TP_INITIAL:.1f}%", values=[f"{x:.1f}%" for x in range(3,100,3)])
        btn_buy = Button(text="COMPRAR", background_color=COLOR_ACCENT_NEON)

        def do_buy(x):
            symbol = symbol_in.text.strip().upper()
            if not symbol.endswith("USDT"):
                symbol += "USDT"
            try:
                invest = float(invest_in.text) if invest_in.text else MIN_PURCHASE_USDT
                invest = max(invest, MIN_PURCHASE_USDT)
                sl = float(sl_spin.text.replace("%",""))
                tp = float(tp_spin.text.replace("%",""))
            except:
                self.alert("Error", "Datos inválidos")
                return
            threading.Thread(target=lambda: self.buy_if_possible(symbol, RealBinanceClientWrapper(self.keys["api"], self.keys["secret"]), investment=invest, sl_pct=sl, tp_pct=tp)).start()
            popup.dismiss()

        btn_buy.bind(on_press=do_buy)
        content.add_widget(Label(text="Compra Manual"))
        content.add_widget(symbol_in)
        content.add_widget(invest_in)
        content.add_widget(Label(text="SL %"))
        content.add_widget(sl_spin)
        content.add_widget(Label(text="TP %"))
        content.add_widget(tp_spin)
        content.add_widget(btn_buy)
        popup = Popup(title="Compra Manual", content=content, size_hint=(0.9,0.7))
        popup.open()

    def check_tp_sl(self, sec, price):
        d = sec.data
        initial_sl_price = d["entry_price"] * (1 - PUMP_SL_INITIAL / 100)
        current_tp_price = d["entry_price"] * (1 + d["tp_pct"] / 100)
        if d["trailing_active"]:
            sl_price = d["max_high"] * (1 - TRAILING_SL_PCT / 100)
        else:
            sl_price = initial_sl_price
        if price > d["max_high"]:
            d["max_high"] = price
        if price >= current_tp_price:
            d["tp_pct"] += PUMP_TP_STEP
            d["trailing_active"] = True
            self.alert("TP ALCANZADO", f"Nuevo TP {d['tp_pct']:.1f}% - Trailing activado")
        if price <= sl_price:
            reason = "SL Trailing" if d["trailing_active"] else "SL Inicial"
            self.sell_section(sec, reason=reason, initial_sl=not d["trailing_active"])

    @mainthread
    def update_section_display(self, sec, price=None):
        w = sec.widgets
        d = sec.data
        if d["estado"] != "COMPRADO":
            for key in w:
                if hasattr(w[key], 'text'):
                    w[key].text = "" if "symbol" in key else "$0.000000" if "price" in key else "0.00" if "cantidad" in key else "$0.00"
                if key == "btn_vender":
                    w[key].disabled = True
                if key == "lbl_state":
                    w[key].text = "INACTIVO"
            return
        if not price:
            price = get_price_usdt(d["moneda"]) or d["entry_price"]
        current_tp_price = d["entry_price"] * (1 + d["tp_pct"] / 100)
        sl_price = d["max_high"] * (1 - TRAILING_SL_PCT / 100) if d["trailing_active"] else d["entry_price"] * (1 - PUMP_SL_INITIAL / 100)
        w["txt_symbol"].text = d["moneda"].replace("USDT", "")
        w["inp_real"].text = f"{price:.6f}"
        w["inp_entry"].text = f"{d['entry_price']:.6f}"
        w["spin_sl"].text = f"{PUMP_SL_INITIAL:.1f}%"
        w["spin_tp"].text = f"{d['tp_pct']:.1f}%"
        w["lbl_sl_price"].text = f"${sl_price:.6f}"
        w["lbl_tp_price"].text = f"${current_tp_price:.6f}"
        w["lbl_p_venta"].text = f"${current_tp_price:.6f}"
        w["lbl_inversion"].text = f"${d['inversion']:.2f}"
        w["lbl_cantidad"].text = f"{d['cantidad']:.4f}"
        w["lbl_state"].text = "TRAILING ACTIVE" if d["trailing_active"] else "COMPRADO"
        w["btn_vender"].disabled = False
        pg = (price * d["cantidad"]) - d["inversion"]
        w["inp_pg"].text = f"${pg:+.2f} USDT"
        w["inp_pg"].background_color = COLOR_ACCENT_NEON if pg >= 0 else COLOR_ACCENT_ERROR

    @mainthread
    def sell_section(self, sec, reason="Manual", initial_sl=False):
        if sec.data["estado"] != "COMPRADO":
            return
        symbol = sec.data["moneda"]
        sell_price = get_price_usdt(symbol) or sec.data["entry_price"]
        client = RealBinanceClientWrapper(self.keys["api"], self.keys["secret"])
        asset = symbol.replace("USDT", "")
        bal = client.get_asset_balance(asset)
        qty_to_sell = float(bal['free']) if bal else 0.0
        if qty_to_sell <= 0:
            qty_to_sell = sec.data["cantidad"]
        qty = self.get_adjusted_qty(symbol, qty_to_sell, is_sell=True) or sec.data["cantidad"]
        order = client.create_market_sell_order(symbol, qty) if qty_to_sell > 0 else None
        pg = (sell_price * qty) - sec.data["inversion"]
        self.acum["acumulado_real"] += pg
        save_acumulado(self.acum)
        self.alert("VENTA OK", f"{symbol} vendido - G/P: ${pg:+.2f} ({reason})")
        if initial_sl:
            self.initial_sl_blacklist.add(symbol)
        else:
            self.subsequent_sl[symbol] = (sell_price, time.time())
        sec.data.update({"estado": "INACTIVO", "moneda": None, "entry_price": 0.0, "cantidad": 0.0, "inversion": 0.0, "max_high": 0.0, "initial_sl_hit": False, "trailing_active": False})
        self.update_section_display(sec)
        self.update_capital()
        save_positions(self.sections)

    def config_api(self, inst):
        content = BoxLayout(orientation="vertical", padding=10, spacing=10)
        api_in = TextInput(hint_text="API Key", text=self.keys.get("api",""))
        sec_in = TextInput(hint_text="Secret Key", password=True, text=self.keys.get("secret",""))
        btn_save = Button(text="GUARDAR", background_color=COLOR_ACCENT_NEON)
        btn_save.bind(on_press=lambda x: (save_api_keys(api_in.text, sec_in.text), popup.dismiss(), self.alert("API", "Claves guardadas")))
        content.add_widget(Label(text="Configurar API Binance"))
        content.add_widget(api_in)
        content.add_widget(sec_in)
        content.add_widget(btn_save)
        popup = Popup(title="Config API", content=content, size_hint=(0.9,0.6))
        popup.open()

    @mainthread
    def show_logs_popup(self, inst):
        if not LOG_LINES:
            self.alert("LOGS", "No hay logs")
            return
        content = BoxLayout(orientation="vertical")
        log_text = TextInput(text="\n".join(LOG_LINES[-500:]), readonly=True, size_hint_y=None, height=800)
        scroll = ScrollView()
        scroll.add_widget(log_text)
        content.add_widget(scroll)
        close_btn = Button(text="CERRAR", size_hint_y=None, height=50)
        close_btn.bind(on_press=lambda x: popup.dismiss())
        content.add_widget(close_btn)
        popup = Popup(title="Logs", content=content, size_hint=(0.95, 0.9))
        popup.open()

    @mainthread
    def alert(self, title, message):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text=message))
        btn = Button(text="OK", size_hint_y=None, height=40)
        popup = Popup(title=title, content=content, size_hint=(0.7, 0.3))
        btn.bind(on_press=popup.dismiss)
        content.add_widget(btn)
        popup.open()

class MagicPumpApp(App):
    def build(self):
        return TradingInterface()

    def on_start(self):
        log("Magic Pump 24/7 iniciado")

    def on_pause(self):
        log("App en background - bot sigue activo")
        return True  # ¡¡CLAVE PARA 24/7!!

    def on_resume(self):
        log("App reanudada")

    def on_stop(self):
        log("App detenida")
        # Liberar wake lock si existe
        root = self.root
        if hasattr(root, 'wake_lock') and root.wake_lock and root.wake_lock.isHeld():
            root.wake_lock.release()
            log("Wake lock liberado")

if _name_ == '_main_':
    MagicPumpApp().run()
