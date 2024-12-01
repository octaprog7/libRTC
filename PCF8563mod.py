# import sys
from collections import namedtuple

from sensor_pack_2.irtc import (int_to_bcd, bcd_to_int, IRTCwAlarms, rtc_time,
                                get_day_of_year, rtc_alarm_time, check_alarm_time, change_bit_by_flags)
from sensor_pack_2 import bus_service
from sensor_pack_2.base_sensor import DeviceEx, Iterator
# from sensor_pack_2.base_sensor import check_value

'''Биты TF и AF: При возникновении сигнала тревоги, AF устанавливается в логическую 1. Аналогично, в конце обратного 
отсчета таймера, бит TF устанавливается в логическую 1. Эти биты сохраняют свое значение до тех пор, пока не будут 
перезаписаны программным обеспечением. Если приложению требуются прерывания таймера и прерывания сигнала тревоги, 
источник прерывания можно определить, прочитав эти биты. Чтобы предотвратить перезапись одного флага при очистке другого, 
во время доступа к записи выполняется логическое И.'''

# состояние RTC:
#   * ext_clock_mode   - 0 - тактирование от внутреннего генератора; 1 - тактирование от внешнего генератора (EXT_CLK).
#   * clock_stopped- 0 - тактирование RTC работает; 1 - тактирование RTC НЕ работает, часы стоят!
#   * POR_disable-   0 - Функция отмены сброса (POR) при включении питания отключена, установите в логический 0 для нормальной работы; 1 - отмена сброса при включении питания может(!) быть включена!
#   * timer_int  - прерывание активно, когда активен(1) TF (в зависимости от состояния флага TIE)
#   * alarm_flag -  0 (чтение) флаг тревоги неактивен
#                   1 (чтение) флаг тревоги активен
#                   0 (запись) флаг тревоги очищен
#                   1 (запись) флаг тревоги остается неизменным
#   * timer_flag    -   0 (чтение) флаг таймера неактивен
#                       1 (чтение) флаг таймера активен
#                       0 (запись) флаг таймера очищен
#                       1 (запись) флаг таймера остается неизменным
#   * alarm_int_enabled - 0 - прерывание будильника отключено/ 1- прерывание будильника ВКЛючено
#   * timer_int_enabled - 0 - прерывание таймера отключено/ 1- прерывание таймера ВКЛючено

# 7.6.1 Control/status 2 register
status_fields = "timer_int alarm_flag timer_flag alarm_int_enabled timer_int_enabled"
status_pcf8563 = namedtuple("status_pcf8563", status_fields)


class PCF8563(DeviceEx, IRTCwAlarms, Iterator):
    """Class for work with PCF8563 clock from NXP Semiconductors. Please read PCF8563 datasheet!"""


    def __init__(self, adapter: bus_service.I2cAdapter, address: int = 0x51):
        IRTCwAlarms.__init__(self)
        DeviceEx.__init__(self, adapter, address, False)
        self._tbuf = bytearray(7)   # для чтения/записи времени
        self._alarm_buf = bytearray(4)  # для чтения/записи тревоги
        # self.control_alarm_interrupt()

    # --- IRTC ---
    def read_raw_time(self) -> bytearray:
        """Считывает время по шине, из чипа RTC, в буфер. Возвращает буфер с данными."""
        buf = self._tbuf
        self.read_buf_from_mem(2, buf)
        return buf

    def write_raw_time(self, buf: bytes) -> int:
        """Записывает время из буфера src по шине, в чип RTC. Возвращает длину буфера в байтах."""
        self.write_buf_to_mem(2, buf)
        return len(buf)

    def raw_to_time(self, buf: bytearray) -> rtc_time:
        """Преобразует содержимое буфера buf, заполненного методом read_raw_time, в именованный кортеж rtc_time.
        Содержимое buf в процессе работы метода изменяется!"""
        # print(f"DBG:buf[6]: {buf[6]}\t{bcd_to_int(buf[6])}")
        for index, val in enumerate(buf):
            if index in (0, 1): # сек, мин
                buf[index] = bcd_to_int(0x7F & buf[index])
            if index in (2, 3): # час, дни месяца
                buf[index] = bcd_to_int(0x3F & buf[index])
            if 4 == index:  # день недели
                buf[index] = 1 + bcd_to_int(0x07 & buf[index])  # 1..7
            if 5 == index:  # месяц
                buf[index] = bcd_to_int(0x1F & buf[index])  # 1..31
        y, m, d = 2_000 + bcd_to_int(buf[6]), buf[5], buf[3]
        doy = get_day_of_year(y, m, d)  # RTC не считает day of year
        return rtc_time(year=y, month=m, day=d, hour=buf[2],
                        min=buf[1], sec=buf[0], day_of_week=buf[4], day_of_year=doy)

    def time_to_raw(self, src: rtc_time) -> bytes:
        """Преобразует именованный кортеж src в содержимое буфера, для записи в чип RTC методом write_raw_time"""
        _val = 0
        _buf = self._tbuf
        for ind in range(7):
            if ind in range(2): # сек, мин
                _val = int_to_bcd(src[5-ind])
            if ind in range(2, 4): # часы, дни месяца
                _val = int_to_bcd(src[5-ind])
            if 4 == ind:    # дни недели
                _val = int_to_bcd(src[6]) - 1
            if 5 == ind: # месяц, год
                _val = int_to_bcd(src[1])
            if 6 == ind: # год
                _val = int_to_bcd(src[0] - 2_000)
            _buf[ind] = _val
        return _buf

    def get_stop_event(self, clear: bool = True) -> bool:
        """Возвращает Истина, если произошел сбой тактирования часов, что может говорить о неверном времени и
        необходимости его установки в верное значение!"""
        reg_val = self.read_reg(0x02, 1)[0] # секунды
        # разместить стираемый флаг в регистре секунд это 'блестящая' идея разработчиков RTC!
        bvl = bool(0x80 & reg_val)
        if clear:   # очистка флага VL
            self.write_reg(0x02, 0x7F & reg_val, 1)
        return bvl

    def get_status(self, raw: bool = True) -> [int, tuple]:
        """Возвращает содержимое регистра состояния, если raw is True, иначе кортеж или именованный кортеж"""
        sreg = self.read_reg(0x01, 1)[0]   # читаю регистр  управления/состояния Control_status_2
        if raw: # возвращаю два байта из двух регистров управления/состояния
            return sreg
        rng = range(4, -1, -1)
        val_gen = (bool(sreg & (1 << i)) for i in rng)   # Control_status_2, один байт
        # timer_int alarm_flag timer_flag alarm_int_enabled timer_int_enabled
        return status_pcf8563(timer_int=next(val_gen), alarm_flag=next(val_gen), timer_flag=next(val_gen),
                              alarm_int_enabled=next(val_gen), timer_int_enabled=next(val_gen))

    def set_status(self, value: [int, tuple]):
        """В регистре состояния, для записи, доступны флаги: TI_TP, AF, TF, AIE, TIE."""
        # только регистр Control_status_2
        if isinstance(value, int):
            self.write_reg(0x01, 0x1F & value, 1)
            return
        self._set_status_flags(value)

    def set_control(self, raw_value: int) -> int:
        """Записывает байт value в регистр состояния/управления 2.
        Читайте документацию на микросхему 8.3.2 Register Control_status_2!"""
        self.set_status(raw_value)
        return 0

    def _set_status_flags(self, flags: status_pcf8563):
        """Устанавливает значения флагов в регистре состояния, если в кортеже они не равны None!
        Сброс в False доступен для флагов: AF(alarm_flag), TF(timer_flag), AIE(alarm_int_enabled), TIE(timer_int_enabled)
        Установка в True/False доступна для флагов. ---"""
        _sts = self.get_status(raw=True)
        # номера битов в регистре состояния, значения которых нужно изменить!
        bit_numb = range(4, -1, -1)
        # возвращает маску по номеру бита для выделения или обнуления, если flags[idx] is None or False
        # _get_mask = lambda idx: 1 << bit_numb[idx] if flags[idx] else ~(1 << bit_numb[idx])
        # flg_ind = range(len(bit_numb))  # индексы кортежа flags
        # генератор маски с учетом None в элементах кортежа
        # bit_mask_gen = (_get_mask(index) for index in flg_ind if not flags[index] is None)
        # for mask in bit_mask_gen:
        #    if mask < 0:
        #        _sts &= mask    # обнуляю бит
        #    else:
        #        _sts |= mask    # бит в 1
        result = change_bit_by_flags(_sts, bit_numb, flags)
        self.set_status(result)

    def get_control(self, raw: bool = True) -> [int, tuple]:
        """Возвращает байт из регистра управления.
        Returns byte from the control register 2."""
        return 0x1F & self.read_reg(0x01, 1)[0]

    # --- IRTCwAlarms ---
    def read_raw_alarm(self, alarm_id: int = 0) -> bytearray:
        """Считывает время тревоги по шине, из чипа RTC, в буфер. Возвращает буфер с данными."""
        _abuf = self._alarm_buf
        self.read_buf_from_mem(0x09, _abuf)
        return _abuf

    def write_raw_alarm(self, buf: bytes, alarm_id: int = 0) -> int:
        """Записывает время тревоги из буфера buf по шине, в чип RTC. Возвращает длину буфера в байтах."""
        _abuf = self._alarm_buf
        self.write_buf_to_mem(0x09, _abuf)
        return len(_abuf)

    def raw_alarm_to_time(self, src: bytes) -> rtc_alarm_time:
        """Преобразует сырые данные тревоги из RTC в rtc_alarm_time"""
        disable_mask = 1 << self.get_bit_disable()

        item = src[0]
        alarm_disabled = disable_mask & item
        _min = bcd_to_int(0x7F & item)
        if alarm_disabled:
            _min = None

        item = src[1]
        alarm_disabled = disable_mask & item
        _hour = bcd_to_int(0x3F & item)
        if alarm_disabled:
            _hour = None

        item = src[2]
        # print(f"DBG:src[2] 0x{src[2]:x}")
        alarm_disabled = disable_mask & item
        _day_of_month = bcd_to_int(0x3F & item)
        if alarm_disabled:
            _day_of_month = None

        item = src[3]
        # print(f"DBG:src[3] 0x{src[3]:x}")
        alarm_disabled = disable_mask & item
        _day_of_week = bcd_to_int(0x07 & item)
        if alarm_disabled:
            _day_of_week = None

        # print(f"DBG: {_day_of_month}\t{_day_of_week}")
        return rtc_alarm_time(date_day=_day_of_month if not _day_of_month is None else _day_of_week,
                              hour=_hour, min=_min)

    def time_to_raw_alarm(self, src: rtc_alarm_time) -> bytes:
        """Преобразует rtc_alarm_time в сырые данные тревоги"""
        check_alarm_time(src)
        _abuf = self._alarm_buf
        disable_mask = 1 << self.get_bit_disable()

        _abuf[0] = disable_mask
        if not src.min is None:
            _abuf[0] = int_to_bcd(src.min)

        _abuf[1] = disable_mask
        if not src.hour is None:
            _abuf[1] = int_to_bcd(src.hour)

        _abuf[2] = _abuf[3] = disable_mask
        if not src.date_day is None:
            if src.date_day < disable_mask: # day of week 0..6
                _abuf[3] = int_to_bcd(src.date_day)
            else:   # day of month 1..31
                _abuf[2] = int_to_bcd(src.date_day - disable_mask)

        return _abuf

    def get_alarms_count(self) -> int:
        return 1

    def get_alarm_flags(self, raw: bool = True, clear: bool = True) -> [int, tuple[bool,...]]:
        """Возвращает флаги срабатывания двух будильников (alarm_id_1, alarm_id_0) и очищает их, если clear равен true!
        Return two clock alarms flag (alarm_id_1, alarm_id_0) and clear it, if clear is true!"""
        _raw = self.get_status(raw=True)
        if clear:
            self.set_status(0xF7 & _raw)
        if raw:
            return _raw
        af = bool(0x08 & _raw)
        # return status_pcf8563(timer_int=None, alarm_flag=af, timer_flag=None, alarm_int_enabled=None, timer_int_enabled=None)
        return af,

    def __next__(self) -> tuple:
        """For support iterating."""
        return self.get_time()