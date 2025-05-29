import network
import socket
import time
import uerrno
from machine import I2S, Pin, Timer

WIFI_SSID = "SM"
WIFI_PASSWORD = "smproiect"

UDP_IP = "0.0.0.0"
AUDIO_UDP_PORT = 12345
CONTROL_UDP_PORT = 12346


SCK_PIN_NUM = 9
WS_PIN_NUM = 10
SD_PIN_NUM = 11


PIN_SEG_A = Pin(0, Pin.OUT, value=1)
PIN_SEG_B = Pin(1, Pin.OUT, value=1)
PIN_SEG_C = Pin(2, Pin.OUT, value=1)
PIN_SEG_D = Pin(3, Pin.OUT, value=1)
PIN_SEG_E = Pin(4, Pin.OUT, value=1)
PIN_SEG_F = Pin(5, Pin.OUT, value=1)
PIN_SEG_G = Pin(6, Pin.OUT, value=1)
PIN_SEG_DP = Pin(7, Pin.OUT, value=1)
segment_pins = [PIN_SEG_A, PIN_SEG_B, PIN_SEG_C, PIN_SEG_D, PIN_SEG_E, PIN_SEG_F, PIN_SEG_G, PIN_SEG_DP]

PIN_DIGIT_1 = Pin(16, Pin.OUT, value=0)
PIN_DIGIT_2 = Pin(17, Pin.OUT, value=0)
PIN_DIGIT_3 = Pin(18, Pin.OUT, value=0)
PIN_DIGIT_4 = Pin(19, Pin.OUT, value=0)
digit_control_pins = [PIN_DIGIT_1, PIN_DIGIT_2, PIN_DIGIT_3, PIN_DIGIT_4]

PIN_LED_VOL_1 = Pin(13, Pin.OUT, value=0)
PIN_LED_VOL_2 = Pin(14, Pin.OUT, value=0)
PIN_LED_VOL_3 = Pin(15, Pin.OUT, value=0)
led_volume_pins = [PIN_LED_VOL_1, PIN_LED_VOL_2, PIN_LED_VOL_3]

digits_7seg = {
    0: (0, 0, 0, 0, 0, 0, 1, 1), 1: (1, 0, 0, 1, 1, 1, 1, 1), 2: (0, 0, 1, 0, 0, 1, 0, 1),
    3: (0, 0, 0, 0, 1, 1, 0, 1), 4: (1, 0, 0, 1, 1, 0, 0, 1), 5: (0, 1, 0, 0, 1, 0, 0, 1),
    6: (0, 1, 0, 0, 0, 0, 0, 1), 7: (0, 0, 0, 1, 1, 1, 1, 1), 8: (0, 0, 0, 0, 0, 0, 0, 1),
    9: (0, 0, 0, 1, 0, 0, 0, 1),
    ' ': (1, 1, 1, 1, 1, 1, 1, 1), '-': (1, 1, 1, 1, 1, 1, 0, 1)
}

wlan = None;
sock_audio = None;
sock_control = None;
audio_out = None
i2s_configured_by_client = False
display_timer = Timer()
active_digit_index = 0
volume_received_from_pc = 75
current_display_volume = 75
last_volume_display_update_time = 0
VOLUME_DISPLAY_UPDATE_INTERVAL_MS = 500
player_status = "STOP"


def init_i2s_on_pico(rate, bits, channels):
    global audio_out, i2s_configured_by_client
    if audio_out: audio_out.deinit(); audio_out = None; print("PICO I2S: Re-initializing...")
    sck_pin_obj = Pin(SCK_PIN_NUM);
    ws_pin_obj = Pin(WS_PIN_NUM);
    sd_pin_obj = Pin(SD_PIN_NUM)
    i2s_format = I2S.MONO if channels == 1 else I2S.STEREO
    try:
        audio_out = I2S(0, sck=sck_pin_obj, ws=ws_pin_obj, sd=sd_pin_obj, mode=I2S.TX,
                        bits=bits, format=i2s_format, rate=rate, ibuf=8192)
        print(f"PICO I2S Initialized: Rate={rate}, Bits={bits}, Ch={channels}")
        i2s_configured_by_client = True;
        return True
    except Exception as e:
        print(f"PICO I2S Init Error: {e}")
        audio_out = None;
        i2s_configured_by_client = False;
        return False


def wifi_connect_pico(ssid, password):
    global wlan
    wlan = network.WLAN(network.STA_IF);
    wlan.active(True)
    if not wlan.isconnected():
        print(f"PICO WiFi: Connecting to {ssid}...");
        wlan.connect(ssid, password)
        max_wait = 15
        while max_wait > 0:
            status_code = wlan.status()
            if status_code < 0 or status_code >= 3: break
            max_wait -= 1;
            print(f"PICO WiFi: Waiting...{max_wait} (Status: {status_code})");
            time.sleep(1)
    if wlan.status() == 3:
        print(f"PICO WiFi: Connected. IP: {wlan.ifconfig()[0]}"); return True
    else:
        print(f"PICO WiFi: Connection Failed. Status: {wlan.status()}"); return False


def set_all_segments_off():
    for pin in segment_pins: pin.value(1)


def set_all_digits_off_anode_common():
    for pin in digit_control_pins: pin.value(0)


def activate_digit_anode_common(digit_idx_to_activate):
    for i, pin in enumerate(digit_control_pins):
        pin.value(1 if i == digit_idx_to_activate else 0)


def display_char_on_segments(char_pattern_tuple):
    for i, seg_pin_value_for_on in enumerate(char_pattern_tuple):
        segment_pins[i].value(seg_pin_value_for_on)


def update_display_multiplex(timer_obj):
    global active_digit_index, current_display_volume
    set_all_digits_off_anode_common()
    set_all_segments_off()
    val_to_show_on_current_digit = ' '
    if active_digit_index == 0:
        val_to_show_on_current_digit = (current_display_volume // 1000) % 10
    elif active_digit_index == 1:
        val_to_show_on_current_digit = (current_display_volume // 100) % 10
    elif active_digit_index == 2:
        val_to_show_on_current_digit = (current_display_volume // 10) % 10
    elif active_digit_index == 3:
        val_to_show_on_current_digit = current_display_volume % 10
    char_pattern = list(digits_7seg.get(val_to_show_on_current_digit, digits_7seg[' ']))
    char_pattern[7] = 1
    display_char_on_segments(tuple(char_pattern))
    activate_digit_anode_common(active_digit_index)
    active_digit_index = (active_digit_index + 1) % len(digit_control_pins)


def update_volume_leds(volume_level):
    PIN_LED_VOL_1.value(0)
    PIN_LED_VOL_2.value(0)
    PIN_LED_VOL_3.value(0)
    if 30 < volume_level <= 60:
        PIN_LED_VOL_1.value(1)
    elif 60 < volume_level <= 90:
        PIN_LED_VOL_1.value(1); PIN_LED_VOL_2.value(1)
    elif volume_level > 90:
        PIN_LED_VOL_1.value(1); PIN_LED_VOL_2.value(1); PIN_LED_VOL_3.value(1)


try:
    print("PICO: Setting initial display and LED pins state...")
    set_all_segments_off()
    set_all_digits_off_anode_common()
    for led_pin in led_volume_pins: led_pin.value(0)
    time.sleep_ms(50)

    if wifi_connect_pico(WIFI_SSID, WIFI_PASSWORD):
        sock_control = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        addr_control = socket.getaddrinfo(UDP_IP, CONTROL_UDP_PORT)[0][-1]
        sock_control.bind(addr_control)
        sock_control.settimeout(15.0)
        print(f"PICO: Listening for CONTROL on UDP port {CONTROL_UDP_PORT}")
        print("PICO: Waiting for initial CONFIG command from client...")
        display_timer.init(freq=240, mode=Timer.PERIODIC, callback=update_display_multiplex)

        while not i2s_configured_by_client:
            try:
                ctrl_data, ctrl_addr = sock_control.recvfrom(128)
                message = ctrl_data.decode('utf-8').strip().upper()
                print(f"PICO CTRL RX (Initial): '{message}' from {ctrl_addr}")
                if message.startswith("CONFIG:"):
                    parts = message.split(':')
                    if len(parts) == 4:
                        try:
                            rate = int(parts[1]);
                            bits = int(parts[2]);
                            channels = int(parts[3])
                            if not init_i2s_on_pico(rate, bits, channels):
                                print("PICO: Failed initial I2S config. Waiting again.")
                        except ValueError:
                            print(f"PICO CTRL: Error parsing CONFIG values in '{message}'")
                    else:
                        print(f"PICO CTRL: Malformed CONFIG message: '{message}'")
                elif message.startswith("VOL:"):
                    try:
                        vol_val = int(message.split(':')[1])
                        volume_received_from_pc = max(0, min(100, vol_val))
                        update_volume_leds(volume_received_from_pc)
                        print(f"PICO CTRL: Volume set to {volume_received_from_pc} (pre-config)")
                    except (ValueError, IndexError):
                        print(f"PICO CTRL: Invalid VOL value in '{message}'")
            except OSError as e:
                if e.args[0] == uerrno.ETIMEDOUT:
                    print("PICO: Timeout waiting for initial CONFIG...")
                else:
                    print(f"PICO CTRL Socket Error (Initial): {e}"); raise
            except Exception as e_init_loop:
                print(f"PICO Error in init loop: {e_init_loop}"); time.sleep(1)

        if not i2s_configured_by_client: raise RuntimeError("No valid I2S CONFIG received from client.")

        sock_audio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        addr_audio = socket.getaddrinfo(UDP_IP, AUDIO_UDP_PORT)[0][-1]
        sock_audio.bind(addr_audio)
        sock_audio.settimeout(0.01)
        print(f"PICO: Listening for AUDIO on UDP port {AUDIO_UDP_PORT}")
        sock_control.settimeout(0.01)
        last_audio_packet_time = time.ticks_ms()
        AUDIO_SILENCE_TIMEOUT_MS = 5000
        print("PICO: Entering main loop...")

        while True:
            current_time_ms = time.ticks_ms()
            new_volume_value_received = False
            try:
                ctrl_data, ctrl_addr = sock_control.recvfrom(128)
                message = ctrl_data.decode('utf-8').strip().upper()
                if message.startswith("CONFIG:"):
                    parts = message.split(':');
                    if len(parts) == 4:
                        try:
                            rate = int(parts[1]); bits = int(parts[2]); channels = int(parts[3]); init_i2s_on_pico(rate,
                                                                                                                   bits,
                                                                                                                   channels)
                        except ValueError:
                            print(f"PICO CTRL: Invalid CONFIG values in '{message}'")
                elif message.startswith("VOL:"):
                    try:
                        vol_val = int(message.split(':')[1])
                        temp_vol = max(0, min(100, vol_val))
                        if temp_vol != volume_received_from_pc:
                            volume_received_from_pc = temp_vol
                            new_volume_value_received = True
                    except (ValueError, IndexError):
                        print(f"PICO CTRL: Invalid VOL value in '{message}'")
                elif message == "PLAY":
                    player_status = "PLAY"
                elif message == "PAUSE":
                    player_status = "PAUSE"
                elif message == "STOP":
                    player_status = "STOP"
            except OSError as e:
                if e.args[0] != uerrno.ETIMEDOUT: print(f"PICO CTRL Socket Error (Loop): {e}")

            if time.ticks_diff(current_time_ms, last_volume_display_update_time) >= VOLUME_DISPLAY_UPDATE_INTERVAL_MS:
                if current_display_volume != volume_received_from_pc:
                    current_display_volume = volume_received_from_pc
                last_volume_display_update_time = current_time_ms

            if new_volume_value_received:
                update_volume_leds(volume_received_from_pc)

            if audio_out and i2s_configured_by_client and player_status == "PLAY":
                try:
                    audio_chunk, audio_addr = sock_audio.recvfrom(2048)
                    if audio_chunk:
                        audio_out.write(audio_chunk)
                        last_audio_packet_time = time.ticks_ms()
                except OSError as e:
                    if e.args[0] == uerrno.ETIMEDOUT:
                        if time.ticks_diff(current_time_ms, last_audio_packet_time) > AUDIO_SILENCE_TIMEOUT_MS:
                            last_audio_packet_time = current_time_ms
    else:
        print("PICO: Halting due to WiFi connection failure.")
except RuntimeError as e:
    print(f"PICO: Fatal runtime error - {e}.")
except KeyboardInterrupt:
    print("PICO: Program stopped by user (KeyboardInterrupt).")
except Exception as e_global:
    print(f"PICO: An unexpected global error occurred: {e_global}")
finally:
    print("PICO: Cleaning up resources...")
    if 'display_timer' in locals() and isinstance(display_timer, Timer):
        display_timer.deinit();
        print("PICO: Display timer deinitialized.")
    set_all_digits_off_anode_common()
    set_all_segments_off()
    for led_pin in led_volume_pins: led_pin.value(0)
    print("PICO: Display and LED pins set to off.")
    if audio_out: print("PICO: Deinitializing I2S."); audio_out.deinit()
    if sock_audio: print("PICO: Closing audio socket."); sock_audio.close()
    if sock_control: print("PICO: Closing control socket."); sock_control.close()
    if wlan and wlan.isconnected(): print("PICO: Disconnecting WiFi."); wlan.disconnect(); wlan.active(False)
    print("PICO: Cleanup complete. Program terminated.")