import cv2
import mediapipe as mp
import numpy as np
import socket
import time
import wave
import os
import threading


mp_hands = mp.solutions.hands
hands = mp_hands.Hands(
    static_image_mode=False, max_num_hands=1,
    min_detection_confidence=0.7, min_tracking_confidence=0.7)
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles


PICO_IP = "192.168.57.15"
PICO_AUDIO_PORT = 12345
PICO_CONTROL_PORT = 12346
sock_audio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock_control = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


AUDIO_FILES_DIR = "C:/SM/WAV"
AUDIO_CHUNK_SIZE_FRAMES = 256

song_list = []
current_song_index = 0
current_wave_file = None
current_song_params = {"framerate": 44100, "channels": 1, "sampwidth": 2}

is_streaming_allowed = False
playback_paused_by_gesture = True
audio_thread_obj = None
audio_thread_stop_event = threading.Event()


last_gesture_command_time = 0
GESTURE_COMMAND_COOLDOWN = 1.5
last_volume_command_time = 0
VOLUME_COMMAND_COOLDOWN = 1.5
current_volume_level = 75



def get_distance_2d(p1, p2, image_width, image_height):
    x1, y1 = int(p1.x * image_width), int(p1.y * image_height)
    x2, y2 = int(p2.x * image_width), int(p2.y * image_height)
    return np.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def map_value(value, in_min, in_max, out_min, out_max):
    value = max(in_min, min(value, in_max))
    if in_min == in_max: return out_min
    return int((value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min)


def is_finger_up(landmarks, finger_tip_id, finger_pip_id, finger_mcp_id):
    tip_y = landmarks[finger_tip_id].y
    pip_y = landmarks[finger_pip_id].y
    mcp_y = landmarks[finger_mcp_id].y
    return tip_y < pip_y and pip_y < (mcp_y + 0.02)


def is_thumb_tucked(landmarks, image_width, image_height, threshold_px=50):
    thumb_tip = landmarks[mp_hands.HandLandmark.THUMB_TIP]
    index_mcp = landmarks[mp_hands.HandLandmark.INDEX_FINGER_MCP]
    middle_mcp = landmarks[mp_hands.HandLandmark.MIDDLE_FINGER_MCP]
    distance_to_index_mcp = get_distance_2d(thumb_tip, index_mcp, image_width, image_height)
    distance_to_middle_mcp = get_distance_2d(thumb_tip, middle_mcp, image_width, image_height)
    return distance_to_index_mcp < threshold_px or distance_to_middle_mcp < threshold_px


def is_thumb_extended(landmarks, image_width, image_height, threshold_px=70):
    thumb_tip = landmarks[mp_hands.HandLandmark.THUMB_TIP]
    pinky_mcp = landmarks[mp_hands.HandLandmark.PINKY_MCP]
    distance_pixels = get_distance_2d(thumb_tip, pinky_mcp, image_width, image_height)
    return distance_pixels > threshold_px


def load_song_list_from_dir():
    global song_list
    song_list = []
    if not os.path.exists(AUDIO_FILES_DIR) or not os.path.isdir(AUDIO_FILES_DIR):
        print(f"EROARE CRITICĂ: Directorul audio '{AUDIO_FILES_DIR}' NU EXISTĂ sau nu este un director!")
        return
    print(f"Se scanează directorul: '{AUDIO_FILES_DIR}'")
    try:
        for f_name in sorted(os.listdir(AUDIO_FILES_DIR)):
            if f_name.lower().endswith(".wav"):
                song_list.append(os.path.join(AUDIO_FILES_DIR, f_name))
        if song_list:
            print(f"S-au încărcat {len(song_list)} melodii.")
        else:
            print(f"Niciun fișier .wav găsit în {AUDIO_FILES_DIR}")
    except Exception as e:
        print(f"Eroare la scanarea directorului '{AUDIO_FILES_DIR}': {e}")


def open_song_for_streaming(song_index):
    global current_wave_file, current_song_params, song_list
    if not (0 <= song_index < len(song_list)):
        print(f"Index melodie invalid: {song_index}. Lista are {len(song_list)} melodii.")
        return False
    filepath = song_list[song_index]
    try:
        if current_wave_file:
            current_wave_file.close()
            current_wave_file = None
        current_wave_file = wave.open(filepath, 'rb')
        current_song_params["framerate"] = current_wave_file.getframerate()
        current_song_params["channels"] = current_wave_file.getnchannels()
        current_song_params["sampwidth"] = current_wave_file.getsampwidth()
        print(f"Deschis '{os.path.basename(filepath)}': {current_song_params['framerate']}Hz, "
              f"{current_song_params['sampwidth'] * 8}-bit, {current_song_params['channels']}ch")
        config_msg = f"CONFIG:{current_song_params['framerate']}:{current_song_params['sampwidth'] * 8}:{current_song_params['channels']}"
        for i in range(3):
            try:
                sock_control.sendto(config_msg.encode(), (PICO_IP, PICO_CONTROL_PORT))
                print(f"Trimis la Pico ({i + 1}/3): {config_msg}")
                time.sleep(0.05 + i * 0.02)
            except Exception as e_send:
                print(f"Eroare la trimiterea CONFIG ({i + 1}/3): {e_send}")
                time.sleep(0.1)
        return True
    except wave.Error as e_wave:
        print(f"Eroare specifică WAV la deschiderea '{filepath}': {e_wave}")
        current_wave_file = None
        return False
    except Exception as e:
        print(f"Eroare generală la deschiderea fișierului WAV {filepath}: {e}")
        current_wave_file = None
        return False


def scale_volume(audio_data_bytes, volume_percentage, sampwidth):
    if not audio_data_bytes: return audio_data_bytes
    if sampwidth != 2: return audio_data_bytes
    if volume_percentage == 100: return audio_data_bytes
    try:
        audio_samples = np.frombuffer(audio_data_bytes, dtype=np.int16)
        volume_factor = volume_percentage / 100.0
        scaled_samples = np.clip(audio_samples * volume_factor, -32768, 32767).astype(np.int16)
        return scaled_samples.tobytes()
    except Exception as e:
        print(f"Eroare la scalarea volumului: {e}")
        return audio_data_bytes


def audio_streamer_thread():
    global is_streaming_allowed, playback_paused_by_gesture, current_wave_file, current_song_params, audio_thread_stop_event, current_volume_level

    print("Thread streamer audio pornit.")
    if not current_wave_file:
        print("Thread: Niciun fișier audio deschis. Oprire thread.")
        audio_thread_stop_event.set()
        return

    if current_song_params["framerate"] <= 0:
        print(f"Thread: Framerate invalid ({current_song_params['framerate']}). Oprire thread.")
        audio_thread_stop_event.set()
        return

    frames_per_chunk = AUDIO_CHUNK_SIZE_FRAMES
    chunk_duration_sec = frames_per_chunk / current_song_params["framerate"]

    while not audio_thread_stop_event.is_set():
        if not is_streaming_allowed or playback_paused_by_gesture:
            time.sleep(0.05)
            continue

        if not current_wave_file:
            print("Thread: Fișierul audio a devenit None. Oprire.")
            break

        try:
            audio_frames = current_wave_file.readframes(frames_per_chunk)
        except (wave.Error, Exception) as e_read:
            print(f"Thread: Eroare la citirea frame-urilor WAV: {e_read}")
            break

        if not audio_frames:
            print("Thread: Sfârșitul melodiei.")
            audio_thread_stop_event.set()
            break

        processed_audio_frames = scale_volume(audio_frames, current_volume_level, current_song_params["sampwidth"])
        try:
            sock_audio.sendto(processed_audio_frames, (PICO_IP, PICO_AUDIO_PORT))
        except (socket.error, Exception) as e_sock:
            print(f"Thread: Eroare socket la trimiterea datelor audio: {e_sock}")
            audio_thread_stop_event.set()
            break


        sleep_time = chunk_duration_sec
        time.sleep(sleep_time)

    print("Thread streamer audio oprit.")


def manage_audio_thread(action):
    global audio_thread_obj, audio_thread_stop_event, is_streaming_allowed, playback_paused_by_gesture, current_song_index, current_wave_file

    print(f"MANAGE_AUDIO: Acțiune = {action}")

    if audio_thread_obj and audio_thread_obj.is_alive():
        print("MANAGE_AUDIO: Se semnalizează oprirea thread-ului audio existent...")
        audio_thread_stop_event.set()
        audio_thread_obj.join(timeout=0.5)
        if audio_thread_obj.is_alive():
            print("MANAGE_AUDIO: AVERTISMENT - Thread-ul audio nu s-a oprit la timp!")
    audio_thread_obj = None

    if current_wave_file:
        try:
            current_wave_file.close()
        except wave.Error:
            pass
        current_wave_file = None

    is_streaming_allowed = False
    playback_paused_by_gesture = True
    audio_thread_stop_event.clear()

    if action == "PLAY":
        if not open_song_for_streaming(current_song_index): return
        if current_wave_file:
            is_streaming_allowed = True
            playback_paused_by_gesture = False
            audio_thread_obj = threading.Thread(target=audio_streamer_thread)
            audio_thread_obj.daemon = True
            audio_thread_obj.start()
            print("MANAGE_AUDIO: Stream audio pornit/reluat.")
            try:
                sock_control.sendto("PLAY".encode(), (PICO_IP, PICO_CONTROL_PORT))
            except Exception as e:
                print(f"Eroare trimitere PLAY la Pico: {e}")
        else:
            print("MANAGE_AUDIO: Eroare, fișierul WAV nu este deschis pentru PLAY.")

    elif action == "PAUSE":
        is_streaming_allowed = True
        playback_paused_by_gesture = True
        print("MANAGE_AUDIO: Stream audio pe pauză.")
        try:
            sock_control.sendto("PAUSE".encode(), (PICO_IP, PICO_CONTROL_PORT))
        except Exception as e:
            print(f"Eroare trimitere PAUSE la Pico: {e}")

    elif action == "NEXT":
        if song_list:
            current_song_index = (current_song_index + 1) % len(song_list)
            print(f"MANAGE_AUDIO: Trecere la melodia următoare (index {current_song_index})")
            try:
                sock_control.sendto("NEXT".encode(), (PICO_IP, PICO_CONTROL_PORT))
            except Exception as e:
                print(f"Eroare trimitere NEXT la Pico: {e}")
            manage_audio_thread("PLAY")

    elif action == "PREV":
        if song_list:
            current_song_index = (current_song_index - 1 + len(song_list)) % len(song_list)
            print(f"MANAGE_AUDIO: Trecere la melodia anterioară (index {current_song_index})")
            try:
                sock_control.sendto("PREV".encode(), (PICO_IP, PICO_CONTROL_PORT))
            except Exception as e:
                print(f"Eroare trimitere PREV la Pico: {e}")
            manage_audio_thread("PLAY")

    elif action == "STOP_FULL":
        is_streaming_allowed = False
        playback_paused_by_gesture = False
        print("MANAGE_AUDIO: Stream audio oprit complet.")
        try:
            sock_control.sendto("STOP".encode(), (PICO_IP, PICO_CONTROL_PORT))
        except Exception as e:
            print(f"Eroare trimitere STOP la Pico: {e}")


def recognize_gestures_and_volume(hand_landmarks, image_width, image_height):
    global last_gesture_command_time, last_volume_command_time, current_volume_level
    landmarks = hand_landmarks.landmark
    L = mp_hands.HandLandmark

    thumb_tckd = is_thumb_tucked(landmarks, image_width, image_height, threshold_px=45)
    thumb_xtnd = is_thumb_extended(landmarks, image_width, image_height, threshold_px=75)
    index_up = is_finger_up(landmarks, L.INDEX_FINGER_TIP, L.INDEX_FINGER_PIP, L.INDEX_FINGER_MCP)
    middle_up = is_finger_up(landmarks, L.MIDDLE_FINGER_TIP, L.MIDDLE_FINGER_PIP, L.MIDDLE_FINGER_MCP)
    ring_up = is_finger_up(landmarks, L.RING_FINGER_TIP, L.RING_FINGER_PIP, L.RING_FINGER_MCP)
    pinky_up = is_finger_up(landmarks, L.PINKY_TIP, L.PINKY_PIP, L.PINKY_MCP)

    gesture_action_taken = None
    current_time = time.time()

    if current_time - last_gesture_command_time > GESTURE_COMMAND_COOLDOWN:
        if thumb_xtnd and index_up and middle_up and ring_up and pinky_up:
            manage_audio_thread("PLAY");
            gesture_action_taken = "PLAY"
        elif not index_up and not middle_up and not ring_up and not pinky_up and thumb_tckd:
            manage_audio_thread("PAUSE");
            gesture_action_taken = "PAUSE"
        elif index_up and middle_up and not ring_up and not pinky_up and thumb_tckd:
            manage_audio_thread("NEXT");
            gesture_action_taken = "NEXT"
        elif index_up and not middle_up and not ring_up and pinky_up and thumb_tckd:
            manage_audio_thread("PREV");
            gesture_action_taken = "PREV"

        if gesture_action_taken:
            print(f"Gesture Action: {gesture_action_taken}")
            last_gesture_command_time = current_time

    if current_time - last_volume_command_time > VOLUME_COMMAND_COOLDOWN:
        if thumb_xtnd and index_up and not middle_up and not ring_up and not pinky_up:
            thumb_lm = landmarks[L.THUMB_TIP]
            index_lm = landmarks[L.INDEX_FINGER_TIP]
            distance_pixels = get_distance_2d(thumb_lm, index_lm, image_width, image_height)

            min_expected_dist = 20
            max_expected_dist = 220
            new_volume = map_value(distance_pixels, min_expected_dist, max_expected_dist, 0, 100)

            if abs(new_volume - current_volume_level) > 2 or new_volume == 0 or new_volume == 100:
                current_volume_level = new_volume
                print(f"Laptop Volume Level: {current_volume_level}% (Dist: {distance_pixels:.0f}px)")
                last_volume_command_time = current_time

                vol_msg = f"VOL:{current_volume_level}"
                try:
                    sock_control.sendto(vol_msg.encode(), (PICO_IP, PICO_CONTROL_PORT))
                    print(f"Sent to Pico: {vol_msg}")
                except Exception as e_send_vol:
                    print(f"Error sending volume to Pico: {e_send_vol}")

    return gesture_action_taken, current_volume_level


load_song_list_from_dir()
if not song_list: print("Nicio melodie găsită. Programul se va opri."); exit()

cap = cv2.VideoCapture(0)
if not cap.isOpened(): print("Cannot open camera"); exit()
ret, frame_test = cap.read()
if not ret: print("Cannot get frame dimensions"); cap.release(); exit()
image_h, image_w, _ = frame_test.shape
print(f"Camera resolution: {image_w}x{image_h}")
print(f"Streaming audio to {PICO_IP}:{PICO_AUDIO_PORT}")
print(f"Sending control commands to {PICO_IP}:{PICO_CONTROL_PORT}")
print("Gesturi:")
print("- Palma deschisă (toate degetele extinse): PLAY")
print("- Pumn strâns (degetele strânse, police ascuns): PAUSE")
print("- Index și Mijlociu sus (police ascuns): NEXT")
print("- Index și Deget Mic sus (police ascuns): PREV")
print("- Police și Index extinse (celelalte strânse), distanța variază: Volum")

active_command_display = "INIT"

if not open_song_for_streaming(current_song_index):
    print("Nu s-a putut deschide prima melodie pentru configurare. Ieșire.")
    if cap.isOpened(): cap.release()
    exit()
manage_audio_thread("PAUSE")
time.sleep(0.2)
try:

    initial_vol_msg = f"VOL:{current_volume_level}"
    sock_control.sendto(initial_vol_msg.encode(), (PICO_IP, PICO_CONTROL_PORT))
    print(f"Sent initial volume to Pico: {initial_vol_msg}")
except Exception as e:
    print(f"Error sending initial volume: {e}")

while cap.isOpened():
    success, image = cap.read()
    if not success:
        print("Ignored empty camera frame.")
        continue
    image = cv2.flip(image, 1)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = hands.process(image_rgb)

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_drawing.draw_landmarks(image, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                                      mp_drawing_styles.get_default_hand_landmarks_style(),
                                      mp_drawing_styles.get_default_hand_connections_style())

            recognized_gesture_action, _ = recognize_gestures_and_volume(hand_landmarks, image_w, image_h)
            if recognized_gesture_action:
                active_command_display = recognized_gesture_action

            L = mp_hands.HandLandmark
            thumb_xtnd_draw = is_thumb_extended(hand_landmarks.landmark, image_w, image_h)
            index_up_draw = is_finger_up(hand_landmarks.landmark, L.INDEX_FINGER_TIP, L.INDEX_FINGER_PIP,
                                         L.INDEX_FINGER_MCP)
            middle_up_draw = is_finger_up(hand_landmarks.landmark, L.MIDDLE_FINGER_TIP, L.MIDDLE_FINGER_PIP,
                                          L.MIDDLE_FINGER_MCP)
            ring_up_draw = is_finger_up(hand_landmarks.landmark, L.RING_FINGER_TIP, L.RING_FINGER_PIP,
                                        L.RING_FINGER_MCP)
            pinky_up_draw = is_finger_up(hand_landmarks.landmark, L.PINKY_TIP, L.PINKY_PIP, L.PINKY_MCP)

            if thumb_xtnd_draw and index_up_draw and not middle_up_draw and not ring_up_draw and not pinky_up_draw:
                thumb_tip_pt = hand_landmarks.landmark[L.THUMB_TIP]
                index_tip_pt = hand_landmarks.landmark[L.INDEX_FINGER_TIP]
                cv2.line(image, (int(thumb_tip_pt.x * image_w), int(thumb_tip_pt.y * image_h)),
                         (int(index_tip_pt.x * image_w), int(index_tip_pt.y * image_h)), (255, 0, 255), 3)

    current_display_items = []
    if not is_streaming_allowed:
        state_text = "STOPPED"
    elif playback_paused_by_gesture:
        state_text = "PAUSED"
    else:
        state_text = "PLAYING"

    current_display_items.append(f"Status: {state_text}")
    song_name = "N/A"
    if song_list and 0 <= current_song_index < len(song_list):
        song_name = os.path.basename(song_list[current_song_index])
    current_display_items.append(f"Song: {song_name}")
    current_display_items.append(f"Vol: {current_volume_level}%")

    display_text_on_screen = " | ".join(current_display_items)
    cv2.putText(image, display_text_on_screen, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)

    cv2.imshow('Hand Gesture Music Streamer - Laptop', image)
    if cv2.waitKey(5) & 0xFF == ord('q'):
        break

print("Se oprește stream-ul audio...")
manage_audio_thread("STOP_FULL")
print("Se eliberează resursele...")
if cap.isOpened(): cap.release()
cv2.destroyAllWindows()
if 'hands' in globals() and hands: hands.close()
if sock_audio: sock_audio.close()
if sock_control: sock_control.close()
print("Program laptop încheiat.")