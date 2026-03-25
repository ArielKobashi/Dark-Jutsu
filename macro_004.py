import time
from pynput import mouse, keyboard  # type: ignore
from macro_controls import ExecutionController, StopRequested, handle_custom_event, sleep_with_controls

events = [
    (1.3435566425323486, 'move', {'x': 527, 'y': 646}),  # 001
    (1.3591828346252441, 'move', {'x': 527, 'y': 647}),  # 002
    (1.3671979904174805, 'move', {'x': 527, 'y': 648}),  # 003
    (1.3753538131713867, 'move', {'x': 527, 'y': 649}),  # 004
    (1.3835437297821045, 'move', {'x': 527, 'y': 650}),  # 005
    (1.3913142681121826, 'move', {'x': 527, 'y': 651}),  # 006
    (1.3995184898376465, 'move', {'x': 527, 'y': 651}),  # 007
    (1.407637596130371, 'move', {'x': 527, 'y': 651}),  # 008
    (1.415531873703003, 'move', {'x': 527, 'y': 652}),  # 009
    (1.4234981536865234, 'move', {'x': 527, 'y': 653}),  # 010
    (1.431544542312622, 'move', {'x': 527, 'y': 654}),  # 011
    (1.4394795894622803, 'move', {'x': 526, 'y': 654}),  # 012
    (1.4475407600402832, 'move', {'x': 526, 'y': 655}),  # 013
    (1.455540657043457, 'move', {'x': 526, 'y': 656}),  # 014
    (1.4635355472564697, 'move', {'x': 526, 'y': 657}),  # 015
    (1.4715256690979004, 'move', {'x': 526, 'y': 658}),  # 016
    (1.4795143604278564, 'move', {'x': 525, 'y': 658}),  # 017
    (1.4875481128692627, 'move', {'x': 525, 'y': 660}),  # 018
    (1.4955229759216309, 'move', {'x': 524, 'y': 660}),  # 019
    (1.5033369064331055, 'move', {'x': 524, 'y': 662}),  # 020
    (1.5113790035247803, 'move', {'x': 523, 'y': 663}),  # 021
    (1.5194945335388184, 'move', {'x': 523, 'y': 663}),  # 022
    (1.5274531841278076, 'move', {'x': 523, 'y': 665}),  # 023
    (1.5354821681976318, 'move', {'x': 522, 'y': 666}),  # 024
    (1.5432891845703125, 'move', {'x': 522, 'y': 667}),  # 025
    (1.5514795780181885, 'move', {'x': 522, 'y': 668}),  # 026
    (1.5593340396881104, 'move', {'x': 522, 'y': 669}),  # 027
    (1.567549228668213, 'move', {'x': 521, 'y': 670}),  # 028
    (1.5754039287567139, 'move', {'x': 520, 'y': 671}),  # 029
    (1.5835425853729248, 'move', {'x': 519, 'y': 673}),  # 030
    (1.5915954113006592, 'move', {'x': 518, 'y': 675}),  # 031
    (1.5995407104492188, 'move', {'x': 518, 'y': 677}),  # 032
    (1.607527256011963, 'move', {'x': 517, 'y': 678}),  # 033
    (1.6154913902282715, 'move', {'x': 517, 'y': 680}),  # 034
    (1.6234335899353027, 'move', {'x': 516, 'y': 682}),  # 035
    (1.6314687728881836, 'move', {'x': 515, 'y': 683}),  # 036
    (1.6393632888793945, 'move', {'x': 514, 'y': 685}),  # 037
    (1.6474967002868652, 'move', {'x': 514, 'y': 687}),  # 038
    (1.6554248332977295, 'move', {'x': 514, 'y': 688}),  # 039
    (1.6634821891784668, 'move', {'x': 512, 'y': 691}),  # 040
    (1.6714210510253906, 'move', {'x': 512, 'y': 693}),  # 041
    (1.6794862747192383, 'move', {'x': 511, 'y': 695}),  # 042
    (1.6874456405639648, 'move', {'x': 510, 'y': 698}),  # 043
    (1.6952693462371826, 'move', {'x': 509, 'y': 700}),  # 044
    (1.703361988067627, 'move', {'x': 509, 'y': 702}),  # 045
    (1.7113301753997803, 'move', {'x': 508, 'y': 704}),  # 046
    (1.7195324897766113, 'move', {'x': 508, 'y': 706}),  # 047
    (1.7273390293121338, 'move', {'x': 507, 'y': 708}),  # 048
    (1.7355051040649414, 'move', {'x': 507, 'y': 712}),  # 049
    (1.7432758808135986, 'move', {'x': 507, 'y': 714}),  # 050
    (1.7513058185577393, 'move', {'x': 506, 'y': 715}),  # 051
    (1.7592747211456299, 'move', {'x': 505, 'y': 717}),  # 052
    (1.7674100399017334, 'move', {'x': 505, 'y': 719}),  # 053
    (1.7753989696502686, 'move', {'x': 504, 'y': 721}),  # 054
    (1.7834186553955078, 'move', {'x': 504, 'y': 723}),  # 055
    (1.791398286819458, 'move', {'x': 503, 'y': 724}),  # 056
    (1.799415111541748, 'move', {'x': 503, 'y': 726}),  # 057
    (1.8073999881744385, 'move', {'x': 503, 'y': 728}),  # 058
    (1.8154075145721436, 'move', {'x': 503, 'y': 730}),  # 059
    (1.8234319686889648, 'move', {'x': 502, 'y': 731}),  # 060
    (1.8314149379730225, 'move', {'x': 502, 'y': 733}),  # 061
    (1.8394134044647217, 'move', {'x': 502, 'y': 734}),  # 062
    (1.8474054336547852, 'move', {'x': 502, 'y': 734}),  # 063
    (1.8554365634918213, 'move', {'x': 501, 'y': 736}),  # 064
    (1.8633980751037598, 'move', {'x': 501, 'y': 739}),  # 065
    (1.871410608291626, 'move', {'x': 501, 'y': 739}),  # 066
    (1.879399061203003, 'move', {'x': 501, 'y': 743}),  # 067
    (1.8874409198760986, 'move', {'x': 501, 'y': 743}),  # 068
    (1.8953039646148682, 'move', {'x': 501, 'y': 745}),  # 069
    (1.9034457206726074, 'move', {'x': 501, 'y': 746}),  # 070
    (1.9113948345184326, 'move', {'x': 501, 'y': 747}),  # 071
    (1.919426679611206, 'move', {'x': 501, 'y': 748}),  # 072
    (1.927220106124878, 'move', {'x': 501, 'y': 749}),  # 073
    (1.9354228973388672, 'move', {'x': 501, 'y': 750}),  # 074
    (2.4848971366882324, 'click', {'x': 501, 'y': 750, 'button': 'left', 'pressed': True}),  # 075
    (2.5437092781066895, 'click', {'x': 501, 'y': 750, 'button': 'left', 'pressed': False}),  # 076
]

def _parse_button(name):
    try:
        return getattr(mouse.Button, name)
    except Exception:
        return mouse.Button.left

def _parse_key(value):
    if not value:
        return None
    if isinstance(value, str) and value.startswith('Key.'):
        name = value.split('.', 1)[1]
        return getattr(keyboard.Key, name, value)
    return value

def play():
    m = mouse.Controller()
    k = keyboard.Controller()
    controller = ExecutionController()
    last = 0.0
    for t, kind, data in events:
        controller.poll_keypress()
        controller.wait_if_paused()
        if controller.stop_requested:
            controller.close()
            raise StopRequested("Parada solicitada. Encerrando macro.")
        wait = t - last
        if wait > 0:
            if not sleep_with_controls(wait, controller):
                controller.close()
                raise StopRequested("Parada solicitada. Encerrando macro.")
        last = t
        controller.poll_keypress()
        controller.wait_if_paused()
        if controller.stop_requested:
            controller.close()
            raise StopRequested("Parada solicitada. Encerrando macro.")
        if handle_custom_event(kind, data, controller):
            continue
        if kind == 'move':
            m.position = (data['x'], data['y'])
        elif kind == 'click':
            m.position = (data['x'], data['y'])
            btn = _parse_button(data['button'])
            if data['pressed']:
                m.press(btn)
            else:
                m.release(btn)
        elif kind == 'scroll':
            m.position = (data['x'], data['y'])
            m.scroll(data['dx'], data['dy'])
        elif kind == 'key_down':
            key = _parse_key(data.get('key'))
            if key is not None:
                k.press(key)
        elif kind == 'key_up':
            key = _parse_key(data.get('key'))
            if key is not None:
                k.release(key)
    controller.close()

if __name__ == '__main__':
    play()

