from collections import namedtuple
from sensor_pack_2.base_sensor import check_value
import micropython


@micropython.viper
def bcd_to_int(bcd_byte: int) -> int:
    """преобразует 8 бит bcd в int"""
    # check_value(bcd_byte, range(0, 100), f"Неверное значение 8 bit bcd: {bcd_byte}")
    return (bcd_byte//16*10)+(bcd_byte%16)

@micropython.viper
def int_to_bcd(value: int) -> int:
    """преобразует int в bcd"""
    return (value//10*16)+(value%10)

def is_valid_bcd(bcd_value: int, tetrads: int = 1) -> bool:
    """Проверяет bcd значение на допустимые пределы. tetrads - кол-во тетрад(4 бита), занимаемых bcd значением.
    В одном байте ДВЕ тетрады! Если указать tetrads = 1, то проверит одну младшую тетраду; 2 - проверит один байт!"""
    valid_rng = range(1, 2*4)
    check_value(tetrads, valid_rng, f"Количество тетрад: {tetrads} находится вне допустимого диапазона: {valid_rng}")
    tet_mask = 0x0F
    for index in range(tetrads):
        shift = index << 2
        _mask = tet_mask << shift
        _val = (bcd_value & _mask) >> shift
        if _val > 9:
            return False
    return True

@micropython.native
def get_day_of_year(year: int, month: int, day: int, check: bool = False) -> int:
    """Возвращает номер дня в году 1..366.
    year - год, month - месяц (1..12), day - день месяца(1..31).
    Если check is True, то входные параметры проверяются на правильность!"""
    if check:
        if not year in range(2000, 2100) or not month in range(1, 13) or not day in range(1, 32):
            raise ValueError(f"Неверное значение или года: {year} или месяца: {month} или дня: {day}!")
    n1 = 275 * month // 9
    n2 = (month + 9) // 12
    n3 = (1 + (year - 4 * year // 4 + 2) // 3)
    return n1 - (n2 * n3) + day - 30


# поля кортежа времени тревоги/будильника. чтобы отключить значение, установите его в None!
# date_day - день месяца 1..31 или день недели 0..6. если в седьмом бите этого байта 1, то это день месяца, иначе день недели!
# hour - час, 0..23
# min - минута, 0..59
_alarm_time_fields = "date_day hour min"
# почти то же самое, что и time.struct_time. отсутствует поле tm_isdst
rtc_alarm_time = namedtuple("rtc_alarm_time", _alarm_time_fields)
# year - год, 2000-2099
# month - месяц, 1..12
# day - день месяца, 1..31
# hour - час, 0..23
# min - минута, 0..59
# sec - секунда, 0..59
# day_of_week - день недели 0..6
_time_fields = "year month day hour min sec day_of_week day_of_year"
rtc_time = namedtuple("rtc_time", _time_fields)

def check_alarm_time(_time: rtc_alarm_time, date_bit: int = 7):
    """Проверяет время тревоги на правильность. date_bit - номер бита-признака дня месяца.
    Если в поле date_day этот бит в 1, то это день месяца, иначе день недели!
    Время в 24 часовом формате!"""
    item = _time.min
    if not item is None:
        rng = range(60)
        str_msg = f"Значение {item} вне диапазона {rng}!"
        check_value(item, rng, str_msg)

    item = _time.hour
    if not item is None:
        rng = range(24)
        str_msg = f"Значение {item} вне диапазона {rng}!"
        check_value(item, rng, str_msg)

    item = _time.date_day
    if not item is None:
        msk = 1 << date_bit
        if msk & item:  # день месяца - date
            # print("день месяца!")
            rng = range(1, 32)
            str_msg = f"Значение {item} вне диапазона {rng}!"
            if not item - msk in rng:
                raise ValueError(str_msg)
        else:  # день недели 0..6
            # print("день недели!")
            rng = range(7)
            str_msg = f"Значение {item} вне диапазона {rng}!"
            check_value(item, rng, str_msg)

def get_bit_mask_gen(bit_numbers: tuple[int,...], flags: tuple[[int, bool],...]):
    """Возвращает генератор битовых маск для битовых операций.
    bit_numbers - кортеж с номерами битов, которые соответствуют в int элементам flags"""
    # возвращает маску для бита по его номеру. Если флаг равен 1, то создается маска для операции OR,
    # иначе создается маска для операции AND
    _get_mask = lambda idx: 1 << bit_numbers[idx] if flags[idx] else ~(1 << bit_numbers[idx])
    # индексы для кортежа флагов
    flag_index = range(len(bit_numbers))
    # пропускаю флаги содержащие None
    bit_mask_gen = (_get_mask(index) for index in flag_index if not flags[index] is None)
    return bit_mask_gen

def change_bit_by_flags(source: int, bit_numbers: [range, tuple[int,...]], flags: tuple[[int, bool],...]) -> int:
    """Изменяет биты с номерами bit_numbers в source в соответствии со значениями флагов flags.
    Возвращает результат, как int"""
    bit_mask_gen = get_bit_mask_gen(bit_numbers, flags)
    _src = source
    for mask in bit_mask_gen:
        if mask < 0:
            _src &= mask  # обнуляю бит
        else:
            _src |= mask  # устанавливаю бит в 1
    return _src


class IRTC:
    """Интерфейс для RTC"""
    def read_raw_time(self) -> bytearray:
        """Считывает время по шине, из чипа RTC, в буфер. Возвращает буфер с данными.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def write_raw_time(self, buf: bytes) -> int:
        """Записывает время из буфера src по шине, в чип RTC. Возвращает длину буфера в байтах.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def raw_to_time(self, buf: bytearray) -> rtc_time:
        """Преобразует содержимое буфера buf, заполненного методом read_raw_time, в именованный кортеж rtc_time.
        Содержимое buf в процессе работы метода изменяется!
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def time_to_raw(self, src: rtc_time) -> bytes:
        """Преобразует именованный кортеж src в содержимое буфера, для записи в чип RTC методом write_raw_time.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def get_time(self) -> [None, rtc_time]:
        """возвращает время"""
        _buf = self.read_raw_time()
        return self.raw_to_time(_buf)

    def set_time(self, value: rtc_time):
        """устанавливает время"""
        _buf = self.time_to_raw(value)
        self.write_raw_time(_buf)

    def get_stop_event(self, clear: bool = True) -> bool:
        """Возвращает Истина, если произошел сбой тактирования часов, что может говорить о неверном времени и
        необходимости его установки в верное значение!
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def get_status(self, raw: bool = True) -> [int, tuple]:
        """Возвращает содержимое регистра состояния, если raw is True, иначе кортеж или именованный кортеж.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def set_status(self, stat: [int, tuple]):
        """Изменяет режим работы RTC."""
        raise NotImplemented

    def get_control(self, raw: bool = True) -> [int, tuple]:
        """Возвращает содержимое регистра управления, если raw is True, иначе кортеж или именованный кортеж"""
        raise NotImplemented

    def set_control(self, value: [int, tuple]):
        """Устанавливает содержимое регистра управления."""
        raise NotImplemented


class IRTCwAlarms(IRTC):
    """Интерфейс для RTC с тревогами/'будильниками'"""
    def __init__(self):
        """конструктор"""
        # IRTC.__init__()
        # номер бита, который в состоянии 1, запрещает часть тревоги (мин, час, день)
        self._alarm_dis_bit = 7

    def read_raw_alarm(self, alarm_id: int = 0) -> bytearray:
        """Считывает время тревоги по шине, из чипа RTC, в буфер. Возвращает буфер с данными.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def write_raw_alarm(self, src: bytes, alarm_id: int = 0) -> int:
        """Записывает время тревоги из буфера buf по шине, в чип RTC. Возвращает длину буфера в байтах.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def raw_alarm_to_time(self, src: bytes) -> rtc_alarm_time:
        """Преобразует сырые данные тревоги из RTC в rtc_alarm_time.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def time_to_raw_alarm(self, src: rtc_alarm_time) -> bytes:
        """Преобразует сырые данные тревоги из RTC в rtc_alarm_time.
        Для переопределения в классе-наследнике!"""
        raise NotImplemented

    def set_alarm(self, alarm_time: [rtc_alarm_time, None], alarm_id: int = 0):
        """устанавливает время срабатывания тревоги/'будильника'. alarm_id - номер 'будильника'"""
        _buf = self.time_to_raw_alarm(alarm_time)
        self.write_raw_alarm(_buf, alarm_id)

    def get_alarm(self, alarm_id: int = 0) -> [rtc_alarm_time, None]:
        """возвращает время срабатывания тревоги/'будильника'. alarm_id - номер 'будильника'"""
        _buf = self.read_raw_alarm(alarm_id)
        return self.raw_alarm_to_time(_buf)

    def set_bit_disable(self, bit_number: int):
        """Устанавливает номер бита, который в состоянии 1, запрещает часть тревоги (мин, час, день).
        В соответствии с документацией на RTC. Обычно это бит номер семь(7)!
        Для переопределения в классе - наследнике!"""
        rng = range(6, 8)
        check_value(bit_number, rng, f"Номер бита {bit_number} вне диапазона {rng}!")
        self._alarm_dis_bit = bit_number

    def get_bit_disable(self) -> int:
        """Возвращает номер бита, который в состоянии 1, запрещает часть тревоги (мин, час, день).
        В соответствии с документацией на RTC. Обычно это бит номер семь(7)!
        Для переопределения в классе - наследнике!"""
        return self._alarm_dis_bit

    def get_alarms_count(self) -> int:
        """Возвращает кол-во тревог/будильников, поддерживаемых RTC"""
        raise NotImplemented

    def get_alarm_flags(self, raw: bool = True, clear: bool = True) -> [int, tuple[bool,...]]:
        """Возвращает флаги тревог в сыром (int), если raw в Истина, или обработанном, если raw в Ложь, (tuple) виде.
        Если clear в Истина, то сбрасывает флаг(и) тревог/будильника.
        _id - номер тревоги/будильника. От 0 до get_alarms_count() - 1."""
        raise NotImplemented
