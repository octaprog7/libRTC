# libRTC
A library for MicroPython that allows you to control a real-time clock (RTC).
Currently contains ds3231mod, PCF8563mod modules for controlling the DS3231 and PCF8563 RTCs respectively.

## Preparation
Simply connect the board with the RTC to an Arduino, ESP or any other board with MicroPython firmware.
Connection pins:

1. VCC
2. GND
3. SDA
4. SCL

Attention! The DS3231 supply voltage is 3.3V or 5V! If you are using a CR2032 Li-Ion backup battery, 
power the DS3231 board only from 3.3V! If the supply voltage is greater than 3.3 V, 
the CR2032 Li-Ion battery will eventually become unusable due to the charging circuit located on the board.

Load the MicroPython firmware into the NANO board (ESP, etc.), and then the files: main.py, ds3231mod.py, PCF8563mod.py and
the entire sensor_pack_2 folder. Then open main.py in your IDE and run it.

## Selecting RTC in the program code
Set clock_ds3231 to 0 if you have a board with DS3231.
Set clock_ds3231 to 1 if you have a board with PCF8563.

# Control interface
Described by methods of the IRTC, IRTCwAlarms classes. Naturally, there are also unique methods.

# Accuracy of the clock 'running'
Depends on:
* the quality of the quartz resonator.
* fluctuations in ambient temperature.
* the age of the quartz crystal - over time, the resonant frequency decreases slightly.

P.S. Don't forget about the 'quality' of the voltage supplying the RTC!

# Photos
## Breadboard
![alt text](https://github.com/octaprog7/libRTC/blob/master/pics/dual_rtc.jpg)
## RTC interrupt handled
![alt text](https://github.com/octaprog7/libRTC/blob/master/pics/8563_irq_handled.png)
libRTC
# Tests: Real Time Clock – DS3231 / PCF8563 / MCP79400 / DS1307
![alt text](https://www.switchdoc.com/2014/12/benchmarks-realtime-clocks-ds3231-pcf8563-mcp79400-ds1307/)