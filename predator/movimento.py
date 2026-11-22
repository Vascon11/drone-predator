"""Limites compartilhados por controle manual, movimento suave e futuras políticas de IA."""
import dataclasses
import math


@dataclasses.dataclass(frozen=True)
class MovimentoConfig:
    """Forças máximas como desvios do manche em torno de 1500 microssegundos."""

    forca_horizontal: float = 60.0
    forca_vertical_sobe: float = 100.0
    forca_vertical_desce: float = 150.0
    forca_giro: float = 40.0

    def __post_init__(self):
        valores = dataclasses.astuple(self)
        if not all(math.isfinite(v) and 0 <= v <= 500 for v in valores):
            raise ValueError("forças devem ser finitas e estar entre 0 e 500")

    def limitar(self, roll=0.0, pitch=0.0, yaw=0.0, acel=0.0):
        """Limita desvios e devolve (roll, pitch, yaw, acelerador)."""
        if not all(math.isfinite(v) for v in (roll, pitch, yaw, acel)):
            raise ValueError("desvios devem ser finitos")
        horizontal = self.forca_horizontal
        roll = max(-horizontal, min(horizontal, roll))
        pitch = max(-horizontal, min(horizontal, pitch))
        yaw = max(-self.forca_giro, min(self.forca_giro, yaw))
        acel = max(-self.forca_vertical_desce, min(self.forca_vertical_sobe, acel))
        return roll, pitch, yaw, acel
