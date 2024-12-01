import micropython
from random import randint
from machine import I2C, Pin
from ds3231maxim import DS3221, status_ds3231
from PCF8563mod import PCF8563
from sensor_pack_2.irtc import rtc_alarm_time   # , rtc_time
from sensor_pack_2.bus_service import I2cAdapter
import time

def show_header(info: str, width: int = 32):
    print(width * "-")
    print(info)
    print(width * "-")

def delay_ms(_val: int):
    time.sleep_ms(_val)

# читай тут: https://docs.micropython.org/en/latest/reference/isr_rules.html
micropython.alloc_emergency_exception_buf(100)

def handle_interrupt(pin):
    print("interrupt handled!")

# вывод GP22 RASPBERRY PI PICO должен быть подключен к выводу ~INT микросхемы RTC!
# у других плат вы должны сами выбрать правильный вывод GPIO
pin_irq = Pin(22, mode=Pin.IN, pull=Pin.PULL_UP)
pin_irq.irq(trigger=Pin.IRQ_FALLING, handler=handle_interrupt)

# True при использовании DS3231
# False при использовании PCF8563
clock_model = 1

if __name__ == '__main__':
    bus = I2C(id=1, scl=Pin(7), sda=Pin(6), freq=400_000)  # на Raspberry Pi Pico
    adapter = I2cAdapter(bus)
    clock = DS3221(adapter=adapter) if 0 == clock_model else PCF8563(adapter=adapter)

    str_show = "DS3231. Работа." if 0 == clock_model else "PCF8563. Работа."
    show_header(str_show)

    print(f"Clock: {clock}")
    status = clock.get_status(raw=False)
    print(f"clock status: {status}")

    # маска, сообщающая о значении дня месяца, бит 7 в 1, если бит 7 в 0, то это день недели 0..6
    day_of_month_mask = 0x80
    print(f"Get Alarm[0]: {clock.get_alarm(alarm_id=0)}")
    at = rtc_alarm_time(date_day = day_of_month_mask | randint(1, 28), hour=4, min=31)
    print(f"Set Alarm[0]: {at}")
    clock.set_alarm(at)
    print(f"Get Alarm[0]: {clock.get_alarm(alarm_id=0)}")

    _stop_event = clock.get_stop_event(clear = True)
    if _stop_event:
        print("Была остановка счета времени!")
        loc_time = time.localtime()
        print(f"Установка времени в 'правильное' значение: {loc_time}")
        clock.set_time(loc_time)
        delay_ms(10)

    for _ in range(3):
        _tm = clock.get_time()
        print(f"Время из RTC: {_tm};")
        delay_ms(1000)

    # sys.exit(0)

    show_header("Работа с тревогой/будильником!")
    print(f"Количество тревог/будильников: {clock.get_alarms_count()}")

    stat = clock.get_status()
    print(f"Регистр состояния: 0x{stat:x}")
    ctrl = clock.get_control()
    print(f"Регистр управления: 0x{ctrl:x}")

    # sys.exit(0)

    print("Alarm times:")
    print("get_alarm(0):", clock.get_alarm(0))
    if 0 == clock_model:
        print("get_alarm(1):", clock.get_alarm(1))

    # Alarm when seconds match (every minute)/Тревога каждый час в определенную минуту!
    at = rtc_alarm_time(date_day = None, hour=None, min=48)
    print(f"Call: set_alarm({at})")
    clock.set_alarm(alarm_time=at, alarm_id=1)  # у PCF8563 параметр alarm_id игнорируется, а у DS3231 не игнорируется!
    print(f"get_alarm(1):", clock.get_alarm())

    #if not clock_ds3231:
    # alarm interrupt enabled (флаг AIE у PCF8563), флаг A2IE у DS3231, оба в первом бите регистра состояния/управления
    _cv = 0x02
    if 0 == clock_model:
        _cv |= 0x04     # бит INTCN для DS3231
    clock.set_control(_cv)

    print(f"Using iterator...")
    for ltime in clock:
        af = clock.get_alarm_flags(raw=False)
        print(f"_ time: {ltime}\talarm flags: {af}")
        time.sleep_ms(1000)
