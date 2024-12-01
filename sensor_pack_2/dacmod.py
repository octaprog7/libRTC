from sensor_pack_2.base_sensor import check_value

def check_percent_rng(value: float, min_percent: float = 0.0, max_percent: float = 100.0):
    """Проверяет попадание value в диапазон min_percent <= value <= max_percent."""
    if value < min_percent or value > max_percent:
        raise ValueError(f"Неверное значение в процентах: {value}")
    return value

def get_value_percent(percent: float, base: [int, float]) -> float:
    """Возвращает значение, равное процентам percent от числа base."""
    return 0.01 * percent * base

class DAC:
    """Интерфейс ЦАП.
    Пока ничего нет!"""
    def __init__(self, resolution: int, unipolar: bool = True):
        """resolution - разрешение ЦАП в битах.
        Если unipolar is True, то выходное напряжение изменяется в диапазоне 0..V_опорное,
        иначе: -V_опорное/2 ... V_опорное/2"""
        check_value(resolution, range(8, 25), f"Неверное значение разрешения ЦАП: {resolution}!")
        self._resolution = resolution
        self._unipolar = unipolar

    def get_out_range(self) -> range:
        """возвращает 'сырой' диапазон значений выходного регистра"""
        if self.unipolar:
            return range(2 ** self.resolution)
        _mx = 2 ** (self.resolution - 1)
        return range(-1 * _mx, -1 + _mx)

    def get_raw(self, percent: float) -> int:
        """Преобразует значение из процентов (0..100) в сырое значение для регистра выходного значения ЦАП."""
        check_percent_rng(percent)
        return int(get_value_percent(percent=percent, base=2 ** self.resolution))

    @property
    def resolution(self) -> int:
        """resolution - разрешение ЦАП в битах"""
        return self._resolution

    @property
    def unipolar(self) -> bool:
        """Если unipolar is True, то выходное напряжение изменяется в диапазоне 0..V_опорное,
        иначе: -V_опорное/2 ... V_опорное/2"""
        return self._unipolar

    def set_output(self, value: [int, float]) -> [None, bytes]:
        """записывает в выходной регистр ЦАП значение.
        Если значение имеет тип int, то будет записано сырое значение, которое должно быть в диапазоне get_out_range!
        Если значение имеет тип float (0.0 .. 100.0 %) то в выходной регистр будет записано сырое значение,
        соответствующее value в % от get_out_range.stop - 1."""
        raise NotImplementedError