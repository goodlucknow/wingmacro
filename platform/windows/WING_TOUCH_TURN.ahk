; Scroll Accelerator + Touch to Cursor
; Combined script for Surface Pro touch-and-turn workflow
; AHK v2

#Requires AutoHotkey v2.0
#SingleInstance Force
Persistent

; ============================================
; SCROLL ACCELERATION CONSTANTS
; ============================================

; Timing thresholds (ms) - 10 levels for smooth acceleration
ACCEL_TIMEOUT := 400
ACCEL_LEVEL9 := 30
ACCEL_LEVEL8 := 34
ACCEL_LEVEL7 := 40
ACCEL_LEVEL6 := 46
ACCEL_LEVEL5 := 54
ACCEL_LEVEL4 := 62
ACCEL_LEVEL3 := 72
ACCEL_LEVEL2 := 85
ACCEL_LEVEL1 := 100

; Scroll amounts per level
SCROLL_9 := 127
SCROLL_8 := 96
SCROLL_7 := 64
SCROLL_6 := 48
SCROLL_5 := 32
SCROLL_4 := 24
SCROLL_3 := 16
SCROLL_2 := 12
SCROLL_1 := 8
SCROLL_0 := 6

; Momentum settings
MOMENTUM_THRESHOLD := 16
MOMENTUM_DECAY := 0.80

; ============================================
; TOUCH-TO-CURSOR CONSTANTS - Surface Pro 4
; ============================================

SCREEN_WIDTH := 2736
SCREEN_HEIGHT := 1824

RAW_X_MIN := 0
RAW_X_MAX := 9600
RAW_Y_MIN := 0
RAW_Y_MAX := 7200

X_OFFSET := 8
Y_OFFSET := 12

; ============================================
; RAW INPUT CONSTANTS
; ============================================

WM_INPUT := 0x00FF
RIDEV_INPUTSINK := 0x00000100
RID_INPUT := 0x10000003

HID_USAGE_PAGE_DIGITIZER := 0x0D
HID_USAGE_DIGITIZER_TOUCH_SCREEN := 0x04
HID_USAGE_DIGITIZER_PEN := 0x02
HID_USAGE_DIGITIZER_FINGER := 0x22

; ============================================
; STATE VARIABLES
; ============================================

; Scroll state
global history := [200, 200, 200, 200, 200]
global historyIndex := 1
global lastScrollTime := 0
global momentum := 0.0
global scrollDirection := 0
global lastDirection := 0

; Touch state
global hGui := 0
global LastTouchX := 0
global LastTouchY := 0

; ============================================
; TRAY SETUP
; ============================================

A_TrayMenu.Delete()
A_TrayMenu.Add("Scroll + Touch: ON", ToggleEnabled)
A_TrayMenu.Check("Scroll + Touch: ON")
A_TrayMenu.Add()
A_TrayMenu.Add("Exit", (*) => ExitApp())
A_TrayMenu.Default := "Scroll + Touch: ON"
A_TrayMenu.ClickCount := 1
A_IconTip := "Scroll + Touch: ON"
TraySetIcon(A_AhkPath, 1)

ToggleEnabled(*) {
    Suspend(-1)
    if (A_IsSuspended) {
        A_TrayMenu.Uncheck("Scroll + Touch: ON")
        A_IconTip := "Scroll + Touch: OFF"
        TraySetIcon("shell32.dll", 110)
        SetTimer(MomentumDecay, 0)
        global momentum := 0.0
    } else {
        A_TrayMenu.Check("Scroll + Touch: ON")
        A_IconTip := "Scroll + Touch: ON"
        TraySetIcon(A_AhkPath, 1)
        SetTimer(MomentumDecay, 8)
    }
}

; ============================================
; HIDDEN GUI FOR RAW INPUT
; ============================================

myGui := Gui()
myGui.Opt("+LastFound")
hGui := WinExist()
myGui.Show("Hide")

; ============================================
; REGISTER FOR RAW TOUCH INPUT
; ============================================

RegisterRawInput() {
    global hGui
    
    structSize := A_PtrSize = 8 ? 16 : 8
    devices := Buffer(structSize * 3, 0)
    
    ; Touchscreen
    NumPut("UShort", HID_USAGE_PAGE_DIGITIZER, devices, 0)
    NumPut("UShort", HID_USAGE_DIGITIZER_TOUCH_SCREEN, devices, 2)
    NumPut("UInt", RIDEV_INPUTSINK, devices, 4)
    NumPut("UPtr", hGui, devices, A_PtrSize = 8 ? 8 : 4)
    
    ; Pen
    offset := structSize
    NumPut("UShort", HID_USAGE_PAGE_DIGITIZER, devices, offset)
    NumPut("UShort", HID_USAGE_DIGITIZER_PEN, devices, offset + 2)
    NumPut("UInt", RIDEV_INPUTSINK, devices, offset + 4)
    NumPut("UPtr", hGui, devices, offset + (A_PtrSize = 8 ? 8 : 4))
    
    ; Finger
    offset := structSize * 2
    NumPut("UShort", HID_USAGE_PAGE_DIGITIZER, devices, offset)
    NumPut("UShort", HID_USAGE_DIGITIZER_FINGER, devices, offset + 2)
    NumPut("UInt", RIDEV_INPUTSINK, devices, offset + 4)
    NumPut("UPtr", hGui, devices, offset + (A_PtrSize = 8 ? 8 : 4))
    
    return DllCall("RegisterRawInputDevices", "Ptr", devices, "UInt", 3, "UInt", structSize)
}

; ============================================
; RAW TOUCH INPUT HANDLER
; ============================================

OnMessage(WM_INPUT, ProcessRawInput)

ProcessRawInput(wParam, lParam, msg, hwnd) {
    global LastTouchX, LastTouchY
    global momentum, scrollDirection, lastDirection, history
    global X_OFFSET, Y_OFFSET
    global RAW_X_MIN, RAW_X_MAX, RAW_Y_MIN, RAW_Y_MAX
    global SCREEN_WIDTH, SCREEN_HEIGHT
    
    ; Get buffer size
    size := 0
    headerSize := A_PtrSize * 2 + 8
    DllCall("GetRawInputData", "UPtr", lParam, "UInt", RID_INPUT, "Ptr", 0, "UInt*", &size, "UInt", headerSize)
    
    if (size = 0)
        return
    
    ; Get raw input data
    rawInput := Buffer(size, 0)
    result := DllCall("GetRawInputData", "UPtr", lParam, "UInt", RID_INPUT, "Ptr", rawInput, "UInt*", &size, "UInt", headerSize)
    
    if (result = -1)
        return
    
    ; Check if HID type (touch/pen)
    dwType := NumGet(rawInput, 0, "UInt")
    if (dwType != 2)
        return
    
    ; Get HID data
    hidOffset := headerSize
    dwSizeHid := NumGet(rawInput, hidOffset, "UInt")
    
    if (dwSizeHid < 14)
        return
    
    dataOffset := hidOffset + 8
    
    ; Check contact state (01 = touch down, 03 = touch held)
    contactState := NumGet(rawInput, dataOffset + 1, "UChar")
    
    if (contactState != 1 && contactState != 3)
        return
    
    ; Read raw coordinates
    rawX := NumGet(rawInput, dataOffset + X_OFFSET, "UShort")
    rawY := NumGet(rawInput, dataOffset + Y_OFFSET, "UShort")
    
    ; Scale to screen coordinates
    screenX := Round((rawX - RAW_X_MIN) / (RAW_X_MAX - RAW_X_MIN) * SCREEN_WIDTH)
    screenY := Round((rawY - RAW_Y_MIN) / (RAW_Y_MAX - RAW_Y_MIN) * SCREEN_HEIGHT)
    
    ; Clamp to screen bounds
    screenX := Max(0, Min(screenX, SCREEN_WIDTH - 1))
    screenY := Max(0, Min(screenY, SCREEN_HEIGHT - 1))
    
    ; Only move if position changed significantly
    if (Abs(screenX - LastTouchX) > 2 || Abs(screenY - LastTouchY) > 2) {
        LastTouchX := screenX
        LastTouchY := screenY
        
        ; CANCEL MOMENTUM when touching new position
        momentum := 0.0
        scrollDirection := 0
        lastDirection := 0
        history := [200, 200, 200, 200, 200]
        
        ; Move cursor
        DllCall("SetCursorPos", "Int", screenX, "Int", screenY)
    }
    
    return 0
}

; ============================================
; MOMENTUM DECAY TIMER
; ============================================

SetTimer(MomentumDecay, 8)

MomentumDecay() {
    global momentum, scrollDirection, MOMENTUM_DECAY
    
    if (Abs(momentum) > 0.8) {
        momentumScroll := Round(momentum)
        if (momentumScroll != 0) {
            SendScroll(momentumScroll)
        }
        momentum := momentum * MOMENTUM_DECAY
    } else if (momentum != 0.0) {
        momentum := 0.0
        scrollDirection := 0
    }
}

; ============================================
; SCROLL HOTKEYS
; ============================================

WheelUp::HandleScroll(1)
WheelDown::HandleScroll(-1)

; ============================================
; SCROLL HANDLER
; ============================================

HandleScroll(direction) {
    global history, historyIndex, lastScrollTime
    global momentum, scrollDirection, lastDirection
    global ACCEL_TIMEOUT
    global ACCEL_LEVEL9, ACCEL_LEVEL8, ACCEL_LEVEL7, ACCEL_LEVEL6, ACCEL_LEVEL5
    global ACCEL_LEVEL4, ACCEL_LEVEL3, ACCEL_LEVEL2, ACCEL_LEVEL1
    global SCROLL_9, SCROLL_8, SCROLL_7, SCROLL_6, SCROLL_5
    global SCROLL_4, SCROLL_3, SCROLL_2, SCROLL_1, SCROLL_0
    global MOMENTUM_THRESHOLD
    
    currentTime := A_TickCount
    
    ; Reset acceleration on direction change
    if (lastDirection != 0 && direction != lastDirection) {
        history := [200, 200, 200, 200, 200]
        momentum := 0.0
    }
    lastDirection := direction
    
    ; Calculate elapsed time
    if (lastScrollTime > 0) {
        elapsed := currentTime - lastScrollTime
    } else {
        elapsed := 200
    }
    
    ; Update rolling average
    history[historyIndex] := elapsed
    historyIndex := Mod(historyIndex, 5) + 1
    
    ; Calculate average
    avgElapsed := (history[1] + history[2] + history[3] + history[4] + history[5]) / 5
    
    ; Determine scroll amount
    if (avgElapsed < ACCEL_LEVEL9) {
        scrollAmount := SCROLL_9
    } else if (avgElapsed < ACCEL_LEVEL8) {
        scrollAmount := SCROLL_8
    } else if (avgElapsed < ACCEL_LEVEL7) {
        scrollAmount := SCROLL_7
    } else if (avgElapsed < ACCEL_LEVEL6) {
        scrollAmount := SCROLL_6
    } else if (avgElapsed < ACCEL_LEVEL5) {
        scrollAmount := SCROLL_5
    } else if (avgElapsed < ACCEL_LEVEL4) {
        scrollAmount := SCROLL_4
    } else if (avgElapsed < ACCEL_LEVEL3) {
        scrollAmount := SCROLL_3
    } else if (avgElapsed < ACCEL_LEVEL2) {
        scrollAmount := SCROLL_2
    } else if (avgElapsed < ACCEL_LEVEL1) {
        scrollAmount := SCROLL_1
    } else if (avgElapsed > ACCEL_TIMEOUT) {
        scrollAmount := SCROLL_0
        history := [200, 200, 200, 200, 200]
    } else {
        scrollAmount := SCROLL_0
    }
    
    ; Cancel momentum if direction changes
    if (scrollDirection != 0 && direction != scrollDirection) {
        momentum := 0.0
    }
    
    ; Calculate graduated momentum
    if (scrollAmount >= 64) {
        momentumMultiplier := 0.75
    } else if (scrollAmount >= 32) {
        momentumMultiplier := 0.55
    } else if (scrollAmount >= 16) {
        momentumMultiplier := 0.35
    } else {
        momentumMultiplier := 0.0
    }
    
    ; Set momentum
    if (scrollAmount >= MOMENTUM_THRESHOLD) {
        momentum := scrollAmount * momentumMultiplier * direction
        scrollDirection := direction
    } else {
        momentum := 0.0
        scrollDirection := 0
    }
    
    ; Update timer
    lastScrollTime := currentTime
    
    ; Send scroll
    SendScroll(scrollAmount * direction)
}

; ============================================
; SEND SCROLL
; ============================================

SendScroll(delta) {
    MouseGetPos(&mouseX, &mouseY, &targetWin)
    
    if (!targetWin)
        return
    
    deltaInt := Round(delta)
    wParam := (deltaInt << 16) | 0
    xPos := mouseX & 0xFFFF
    yPos := mouseY & 0xFFFF
    lParam := (yPos << 16) | xPos
    
    try {
        SendMessage(0x20A, wParam, lParam, , targetWin)
    } catch {
        PostMessage(0x20A, wParam, lParam, , targetWin)
    }
}

; ============================================
; INITIALIZE
; ============================================

if (RegisterRawInput()) {
    TrayTip("Scroll + Touch active", "Touch to position, scroll to adjust", 1)
} else {
    MsgBox("Failed to register touch input. Error: " A_LastError)
}
SetTimer(() => TrayTip(), -2000)
