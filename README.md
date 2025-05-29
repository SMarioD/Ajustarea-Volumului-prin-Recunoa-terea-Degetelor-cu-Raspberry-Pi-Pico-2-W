
# 🎚️ Ajustarea Volumului prin Recunoașterea Degetelor cu Raspberry Pi Pico 2 W

## 📌 Descriere

Acest proiect demonstrează o metodă modernă și intuitivă de control al volumului audio, bazată pe **recunoașterea gesturilor mâinii** captate de camera laptopului. Prin interpretarea numărului și poziției degetelor, sistemul ajustează nivelul volumului și oferă feedback vizual și auditiv în timp real, utilizând o placă **Raspberry Pi Pico 2 W**.

## 🎯 Motivație

Proiectul își propune să ilustreze o interacțiune om-tehnologie naturală, relevantă pentru domenii precum **IoT**, **interfețe inteligente**, și **Embedded Systems**, fiind o alternativă hands-free la metodele clasice de control multimedia.

## 🧠 Funcționalitate

- Controlul volumului în timp real pe baza poziției degetelor.
- Feedback vizual prin LED-uri și display cu 7 segmente.
- Feedback auditiv prin difuzoare și buzzer (backup).
- Comunicare bidirecțională între laptop și Pico prin UDP.
- Streaming audio live de pe laptop către microcontroler.

## 🛠️ Componente Hardware

- 🎥 **Camera laptopului** – pentru captarea gesturilor.
- 🧠 **Raspberry Pi Pico 2 W** – unitatea de control principală.
- 🔌 **Breadboard 830** + fire jumper – conectivitate.
- 📟 **Display LED 4x7 segmente** – afișează volumul curent.
- 🔊 **Amplificator I2S MAX98357A** + **difuzoare 2x 2W**.
- 🔆 **LED-uri (verde, alb, galben)** – feedback vizual pe niveluri.
- 🧲 **Rezistențe 1/4W**, sursă de alimentare.
- 🔉 **Buzzer (opțional)** – pentru semnalizare alternativă.

## 💻 Software

### 📍 Firmware Raspberry Pi Pico 2 W (MicroPython)
- Configurare GPIO pentru LED-uri, display și amplificator.
- Afișare nivel volum în timp real.
- Primire și procesare comenzi prin UDP.

### 📍 Aplicație pe Laptop (Visual Studio + Python)
- Detectare gesturi cu **MediaPipe + OpenCV**.
- Interpretare gesturi:
  - ✋ Palma deschisă → Play
  - ✊ Pumnul → Pauză
  - ✌️ Index + mijlociu → Next
  - 🤘 Index + deget mic → Previous
  - 👌 Policing + index → Control volum
- Streaming audio în timp real (WAV).
- Comenzi transmise prin UDP pe porturi dedicate.

## 🔄 Flux de Funcționare

1. **Inițializare:** Conectare la WiFi, setup hardware.
2. **Captare imagine:** Procesare în timp real a mâinii.
3. **Recunoaștere gesturi:** Interpretare și transmitere comenzi.
4. **Control volum:** Ajustare prin distanță între degete (20–220px → 0–100%).
5. **Feedback:** Display și LED-uri actualizate automat.
6. **Streaming audio:** Transmisie bufferizată din laptop către Pico.

## ⚙️ Tehnologii Cheie

- Raspberry Pi Pico W + MicroPython
- OpenCV & MediaPipe
- UDP Streaming (porturi 12345 - audio, 12346 - control)
- Multiplexare display la 240Hz
- Sincronizare audio și reconectare automată

## 🔧 Posibilități de Extindere

- Recunoaștere vocală pentru control hibrid
- Suport multi-user
- Integrare în sisteme smart home sau automobile
- Funcții adiționale prin noi gesturi

## 🧑‍💻 Autori

- Ana-Maria Chilimon – [ana-maria.chilimon@student.tuiasi.ro](mailto:ana-maria.chilimon@student.tuiasi.ro)
- Raluca-Ștefania Chiriac – [raluca-stefania.chiriac@student.tuiasi.ro](mailto:raluca-stefania.chiriac@student.tuiasi.ro)
- Mario-Daniel Stoian – [mario-daniel.stoian@student.tuias.ro](mailto:mario-daniel.stoian@student.tuias.ro)

## 📚 Bibliografie

- [Proiect pe GitHub](https://github.com/ChiriacRaluca/Proiect-SM)
- [Raspberry Pi Pico 2 W Pinout](https://datasheets.raspberrypi.com/picow/pico-2-w-pinout.pdf)
- [OpenAI Chat](https://chat.openai.com/)
- [Electronics For You – 7 Segment Display](https://www.electronicsforu.com/resources/7-segment-display-pinout-understanding)
