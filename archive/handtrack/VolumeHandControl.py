import cv2
import time
import numpy as np
import HandTrackingModule as htm
import math
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

cWidth, cHeight = 1280, 720
cap = cv2.VideoCapture(0)
cap.set(3, cWidth)
cap.set(4, cHeight)

pTime = 0
cTime = 0

detector = htm.HandDetector()

devices = AudioUtilities.GetSpeakers()
interface = devices.EndpointVolume
volume = cast(interface, POINTER(IAudioEndpointVolume))

volumeRange = volume.GetVolumeRange()
minVol = volumeRange[0]
maxVol = volumeRange[1]
vol = 0
volBar = 400
volPer = 0
currVol = 0
current_vol_db = volume.GetMasterVolumeLevel()
volPer = int(np.interp(current_vol_db, [minVol, maxVol], [0, 100]))
volBar = np.interp(volPer, [0, 100], [400, 150])

while True:
    success, img = cap.read()

    img = detector.findHands(img)
    lmList = detector.findPosition(img, draw = False)
    if len(lmList) != 0:

        x1, y1 = lmList[4][1], lmList[4][2]
        x2, y2 = lmList[8][1], lmList[8][2]
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        cv2.circle(img, (x1, y1), 15, (255, 0, 255), cv2.FILLED)
        cv2.circle(img, (x2, y2), 15, (255, 0, 255), cv2.FILLED)
        cv2.line(img, (x1, y1), (x2, y2), (255, 0, 255), 3)
        cv2.circle(img, (cx, cy), 15, (255, 0, 255), cv2.FILLED)

        length = round(math.hypot(x2-x1, y2-y1), 2)

        vol = np.interp(length, [40, 280], [minVol, maxVol])
        volPer = int(np.interp(length, [40, 280], [0, 100]))
        volBar = np.interp(length, [40, 280], [400, 150])
        
        if length < 40:
            cv2.circle(img, (cx, cy), 15, (0, 255, 0), cv2.FILLED)
        if length > 280:
            cv2.circle(img, (cx, cy), 15, (0, 0, 255), cv2.FILLED)

        volume.SetMasterVolumeLevel(vol, None)
        
    cv2.rectangle(img, (50,150), (85,400), (0,255,0), 3)
    cv2.rectangle(img, (50, int(volBar)), (85,400), (0,255,0), cv2.FILLED)
    cv2.putText(img, f'{int(volPer)}%', (50, 450), cv2.FONT_HERSHEY_PLAIN, 2, (0,255,0), 2)
    
    cTime = time.time()
    fps = 1/(cTime - pTime)
    pTime = cTime
    cv2.putText(img, f'FPS : {int(fps)}', (40,50), cv2.FONT_HERSHEY_COMPLEX, 1, (255, 0, 0),3)

    cv2.imshow("Volume Controller", img)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
    