from .new_bin_attack import generate as new_bin_attack
from .session_replay import generate as session_replay
from .synthetic_id_ring import generate as synthetic_id_ring

INJECTORS = {
    "new_bin_attack": new_bin_attack,
    "session_replay": session_replay,
    "synthetic_id_ring": synthetic_id_ring,
}
