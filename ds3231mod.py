from collections import namedtuple

from sensor_pack_2.irtc import (int_to_bcd, bcd_to_int, IRTCwAlarms, rtc_time,
                                get_day_of_year, rtc_alarm_time, check_alarm_time, change_bit_by_flags)
from sensor_pack_2 import bus_service   # , base_sensor
from sensor_pack_2.base_sensor import DeviceEx, Iterator
from sensor_pack_2.base_sensor import check_value

# состояние RTC:
#   * OSF   -   Этот бит устанавливается в логическую 1 каждый раз, когда генератор останавливается.
#   * EN32KHz   - При установке в логическую 1, вывод 32 кГц включен и выводит прямоугольный сигнал 32768 кГц.
#   * BSY   -   Этот бит указывает, что устройство занято выполнением измерения температуры.
#   * A2F   -   Логическая 1 в бите флага сигнала тревоги 2 указывает, что время соответствует регистрам сигнала тревоги 2.
#   * A1F   -   Логическая 1 в бите флага сигнала тревоги 1 указывает, что время соответствует регистрам сигнала тревоги 2.
status_ds3231 = namedtuple("status_ds3231", "OSF EN32KHz BSY A2F A1F")
# для внутреннего использования
# start_addr - начальный адрес 'тревоги'
# bytes_count - кол-во байт тревоги
# _alarm_info = namedtuple("_alarm_info", "id start_addr, bytes_count")

class DS3221(DeviceEx, IRTCwAlarms, Iterator):
    """Class for work with DS3231 clock from Maxim Integrated или как эта фирма сейчас называется!?
    Please read DS3231 datasheet!"""
    #           alarm 1 register masks            alarm 2 register masks
    _mask_alarms = (0x0E, 0x0C, 0x08, 0x00, 0x10), (0x06, 0x04, 0x00, 0x08)

    @staticmethod
    def _get_alarm_mask(alarm_id: int):
        return DS3221._mask_alarms[alarm_id]

    @staticmethod
    def _convert_hours(hour_byte: int) -> int:
        # In the 24-hour mode, bit 5 is the 20-hour bit (20–23 hours)
        hour = bcd_to_int(hour_byte & 0x3F)
        if hour_byte & 0x40:    # When high, 12-hour mode is selected
            hour = bcd_to_int(hour_byte & 0x1F)
            if hour_byte & 0x20:    # AM/PM bit with logic-high being PM
                hour = 12 + hour_byte
        return hour

    @staticmethod
    def _get_day_or_date(value: int) -> int:
        """Возвращает день недели или день месяца из value.
        Return day of week or day of month by value."""
        if 0x40 & value:
            return bcd_to_int(0x0F & value)     # day of week
        else:
            return bcd_to_int(0x3F & value)     # day of month

    def __init__(self, adapter: bus_service.I2cAdapter, address: int = 0x68):
        # super().__init__(adapter, address, False)
        IRTCwAlarms.__init__(self)
        DeviceEx.__init__(self, adapter, address, False)
        self._tbuf = bytearray(7)
        self._alarm_buf = bytearray(3)  # только три байта под буфер тревог. секунды не нужны!
        # self._alrm_dis_bit = 7
        # содержимое регистра управления до инициализации!
        # если(!) оно равно 0x1C, то в результате потери питания было сброшено время,
        # поэтому нужно установить правильное время!
        self._ctrl_on_init = self.get_control()
        # off alarm interrupt
        self.control_alarm_interrupt(False, False)

    def read_raw_time(self) -> bytearray:
        """Считывает время по шине, из чипа RTC, в буфер. Возвращает буфер с данными.
        Для переопределения в классе-наследнике!"""
        buf = self._tbuf
        self.read_buf_from_mem(0, buf)
        return buf

    def write_raw_time(self, buf: bytes) -> int:
        """Записывает время из буфера src по шине, в чип RTC. Возвращает длину буфера в байтах.
        Для переопределения в классе-наследнике!"""
        _buf = self._tbuf
        return self.write_buf_to_mem(0, _buf)

    def raw_to_time(self, buf: bytearray) -> rtc_time:
        """Преобразует содержимое буфера buf, заполненного методом read_raw_time, в именованный кортеж rtc_time.
        Содержимое buf в процессе работы метода изменяется!
        Для переопределения в классе-наследнике!"""
        mask = 0x1f
        for i, val in enumerate(buf):
            if i in (0, 1, 4, 6):
                buf[i] = bcd_to_int(val)
            if 2 == i:  # hours
                buf[i] = DS3221._convert_hours(val)
            if 5 == i:  # month
                buf[i] = bcd_to_int(val & mask)
        # -----       YY       MM      DD      HH      MM      SS    WDAY    no year day
        y, m, d = 2_000 + buf[6], buf[5], buf[4]
        doy = get_day_of_year(y, m, d)  # RTC не считает day of year
        return rtc_time(year=y, month=m, day=d, hour=buf[2],
                        min=buf[1], sec=buf[0], day_of_week=buf[3] - 1, day_of_year=doy)

    def time_to_raw(self, src: rtc_time) -> bytes:
        """Преобразует именованный кортеж src в содержимое буфера, для записи в чип RTC методом write_raw_time.
        Для переопределения в классе-наследнике!"""
        k = 5, 4, 3, 6, 2, 1, 0
        v = 3, 5, 6     # day, month, year indexes
        _val = 0
        _buf = self._tbuf
        for ind in range(7):
            if ind not in v:
                _val = int_to_bcd(src[k[ind]])
            else:
                if 3 == ind:  # день недели в RTC начинается с 1!
                    _val = int_to_bcd(src[k[ind]] + 1)
                if 5 == ind:  # месяц
                    _val = int_to_bcd(src[k[ind]])
                if 6 == ind:  # YEAR
                    _val = int_to_bcd(src[k[ind]] - 2_000)
            _buf[ind] = _val
        # for ind in range(7):
        return _buf

    #"""№ bit                Description
    #----------------------------------------------------
    #    Bit 7:              Oscillator Stop Flag (OSF)
    #    Bit 3:              Enable 32kHz Output
    #    Bit 1:              Alarm 2 Flag (A2F)
    #    Bit 0:              Alarm 1 Flag (A1F)
    #"""
    def get_status(self, raw: bool = True) -> [int, status_ds3231]:
        """Возвращает 8 bit регистра состояния, если raw is True, иначе именованный кортеж типа status_ds3231"""
        sreg = self.read_reg(0x0F, 1)[0]
        if raw:
            return sreg
        val_gen = (bool(sreg & (1 << i)) for i in (7, 3, 2, 1, 0))
        return status_ds3231(OSF=next(val_gen), EN32KHz=next(val_gen),
                             BSY=next(val_gen), A2F=next(val_gen), A1F=next(val_gen))

    #"""№ bit                Description
    #----------------------------------------------------
    #    Bit 7:              Enable Oscillator (EOSC)
    #    Bit 6:              Battery-Backed Square-Wave Enable (BBSQW)
    #    Bit 5:              Convert Temperature (CONV)
    #    Bits 4 and 3:       Rate Select (RS2 and RS1)
    #    Bit 2:              Interrupt Control (INTCN)
    #    Bit 1:              Alarm 2 Interrupt Enable (A2IE)
    #    Bit 0:              Alarm 1 Interrupt Enable (A1IE)
    #"""
    def set_status(self, value: [int, status_ds3231]):
        """В регистре состояния, для записи, доступны четыре флага: OSF, EN32kHz, A2F, A1F.
        Флаги A1F, A2F нельзя устанавливать в '1'!!!"""
        if isinstance(value, int):
            self.write_reg(0x0F, value, 1)
            return
        self._set_status_flags(value)

    def _set_status_flags(self, flags: status_ds3231):
        """Устанавливает значения флагов в регистре состояния, если в кортеже они не равны None!
        Сброс в False доступен для флага OSF, A2F, A1F
        Установка в True/False доступна для флага EN32kHz.
        Установка флагов A2F, A1F в 1 приводит к непредсказуемым результатам в работе RTC!"""
        _sts = self.get_status(raw=True)
        bit_numb = 7, 3, 2, 1, 0
        result = change_bit_by_flags(_sts, bit_numb, flags)
        self.set_status(result)

    def get_alarm_flags(self, raw: bool = True, clear: bool = True) -> [int, tuple[bool,...]]:
        """Возвращает флаги срабатывания двух будильников (alarm_id_1, alarm_id_0) и очищает их, если clear равен true!
        Return two clock alarms flag (alarm_id_1, alarm_id_0) and clear it, if clear is true!"""
        _raw = self.get_status(raw=True)
        if clear:
            self.set_status(0xFC & _raw)
        if raw:
            return 0x03 & _raw  # возврат битов 1 и 0 регистра состояния
        # return status_ds3231(OSF=None, EN32KHz=None, BSY=None, A2F=a2, A1F=a1)
        return bool(_raw & 0x02), bool(_raw & 0x01)

    def get_control(self, raw: bool = True) -> [int, tuple]:
        """Возвращает байт из регистра управления.
        Returns byte from the control register."""
        return self.read_reg(0x0E, 1)[0]

    def set_control(self, raw_value: int) -> int:
        """Записывает байт value в регистр управления.
        Читайте документацию на микросхему (Control Register (0Eh))!"""
        return self.write_reg(0x0E, raw_value, 1)

    def get_stop_event(self, clear: bool = True) -> bool:
        """Возвращает Истина, если произошел сбой тактирования часов, что может говорить о неверном времени и
        необходимости его установки в верное значение!"""
        status = self.get_status(raw=False)
        if clear:
            # очистка флага 'Oscillator Stop Flag'
            self.set_status(status_ds3231(OSF=False, EN32KHz=None, BSY=None, A2F=None, A1F=None))
        _x = 0x1C == self._get_ctrl_on_init()
        return status.OSF or _x

    #def get_temperature(self) -> float:
    #    """возвращает температуру микросхемы часов в градусах Цельсия"""
    #    hi, low = self.read_reg(0x11, 2)
    #    return self.unpack("b", hi.to_bytes(1, sys.byteorder))[0] + 0.25 * (low >> 6)

    def get_aging_offset(self) -> int:
        """Возвращает значение подстроечной емкости на выводах кварцевого резонатора. Для компенсации 'ухода' времени!
        Положительные значения добавляют емкость, замедляя частоту генератора. Счет времени пойдет медленнее!
        Отрицательные значения уменьшают емкость, увеличивая частоту генератора. Счет времени пойдет быстрее!
        Для 'тонкой' настройки в очень небольшом диапазоне!"""
        return self.read_reg(0x10, 1)[0]

    def set_aging_offset(self, value: int):
        """Устанавливает значение подстроечной емкости на выводах кварцевого резонатора. Для компенсации 'ухода' времени!"""
        check_value(value, range(-128, 128), f"Неверное значение подстройки частоты: {value}")
        self.write_reg(0x10, value, 1)

    @staticmethod
    def _get_alarm_addr_by_id(alarm_id: int) -> int:
        return 0x08 if 0 == alarm_id else 0x0B      # адрес 0x07 пропускаю. секунды не нужны!

    # ---IRTCwAlarms---
    def read_raw_alarm(self, alarm_id: int = 0) -> bytearray:
        """Считывает время тревоги по шине, из чипа RTC, в буфер. Возвращает буфер с данными."""
        _abuf = self._alarm_buf
        _addr = DS3221._get_alarm_addr_by_id(alarm_id)
        self.read_buf_from_mem(_addr, _abuf)
        return _abuf    # в первом байте - минуты; во втором - часы; в третьем - день недели 1..7/месяца 1..31;

    def write_raw_alarm(self, buf: bytes, alarm_id: int = 0) -> int:
        """Записывает время тревоги из буфера buf по шине, в чип RTC. Возвращает длину буфера в байтах."""
        _abuf = self._alarm_buf
        _addr = DS3221._get_alarm_addr_by_id(alarm_id)
        self.write_buf_to_mem(_addr, _abuf)
        if 0 == alarm_id:
            _dis = 0
            # _dis = 1 << self.get_bit_disable()
            # устанавливаю секунды в ноль
            self.write_reg(_addr - 1, _dis, 1)
        return len(_abuf)

    def raw_alarm_to_time(self, src: bytes) -> rtc_alarm_time:
        """Преобразует сырые данные тревоги из RTC в rtc_alarm_time.
        Для переопределения в классе-наследнике!"""
        disable_mask = 1 << self.get_bit_disable()

        item = src[0]   # минуты
        alarm_disabled = disable_mask & item
        _min = None
        if not alarm_disabled:
            _min = bcd_to_int(0x7F & item)

        item = src[1]   # часы
        alarm_disabled = disable_mask & item
        _hour = None
        if not alarm_disabled:
            _hour = bcd_to_int(0x3F & item)

        item = src[2]   # дни. если в шестом бите 0, то это день месяца, иначе - день недели 1..7
        alarm_disabled = disable_mask & item
        _day_of_month = None
        _day_of_week = None
        if not alarm_disabled:
            if 0x40 & item:     # dy_dt
                _day_of_week = bcd_to_int(0x07 & item) - 1
            else:
                _day_of_month = bcd_to_int(0x3F & item)

        return rtc_alarm_time(date_day=_day_of_month if not _day_of_month is None else _day_of_week,
                              hour=_hour, min=_min)

    def time_to_raw_alarm(self, src: rtc_alarm_time) -> bytes:
        """Преобразует сырые данные тревоги из RTC в rtc_alarm_time.
        Для переопределения в классе-наследнике!"""
        check_alarm_time(src)
        _abuf = self._alarm_buf
        disable_mask = 1 << self.get_bit_disable()

        _abuf[0] = disable_mask
        if not src.min is None:     # минуты
            _abuf[0] = int_to_bcd(src.min)

        _abuf[1] = disable_mask
        if not src.hour is None:    # часы
            _abuf[1] = int_to_bcd(src.hour)

        _abuf[2] = disable_mask
        if not src.date_day is None:
            if src.date_day < disable_mask:  # day of week 0..6
                _abuf[2] = int_to_bcd(src.date_day)
            else:  # day of month 1..31
                _abuf[2] = int_to_bcd(src.date_day - disable_mask)

        return _abuf

    def control_alarm_interrupt(self, irq_alarm_1_enable: bool = False, irq_alarm_0_enable: bool = False):
        """Включает или отключает прерывание от будильников (два) на выводе микросхемы INT/SQW.
        Если вы не используете прерывание, вы должны вызвать метод get_alarm_flags в цикле для обнаружения
        срабатывания будильника!
        Enable or disable two clock alarms interrupt on chip pin INT/SQW.
        If you dont use interrupt, you must call get_alarm_flags method in cycle for detect clock alarm!"""
        cr = self.get_control()
        cr &= 0x18  # BBSQW = INTCN = A2IE = A1IE = 0
        if irq_alarm_1_enable:
            cr |= 0x06  # INTCN = A2IE = 1
        if irq_alarm_0_enable:
            cr |= 0x05  # INTCN = A1IE = 1
        self.set_control(cr)

    def get_alarms_count(self) -> int:
        return 2

    def _get_ctrl_on_init(self) -> int:
        """Cодержимое регистра управления до инициализации!
        если(!) оно равно 0x1C, то в результате потери питания было сброшено время,
        поэтому нужно(!) установить правильное время!"""
        return self._ctrl_on_init

    def __next__(self) -> tuple:
        """For support iterating."""
        return self.get_time()
