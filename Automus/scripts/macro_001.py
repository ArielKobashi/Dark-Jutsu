import time
from pynput import mouse, keyboard  # type: ignore 12
from controladordeatualização import ExecutionController, StopRequested, handle_custom_event, sleep_with_controls

events = [
    (0.0500000000000000, 'focus_totvs_window', {'titles': ['TOTVS SmartClient HTML', 'TOTVS Manufatura'], 'timeout': 10, 'interval': 0.2, 'error_on_timeout': True, 'post_wait': 0.3, 'label': 'macro_001 foco janela totvs'}),  # 001
    (0.2500000000000000, 'wait', {'seconds': 0.15}),  # 002
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
    controller.set_macro_context(__name__, len(events))
    last = 0.0
    for idx, (t, kind, data) in enumerate(events, start=1):
        controller.update_event_position(idx - 1, idx, len(events))
        controller.poll_keypress()
        controller.wait_if_paused()
        if controller.stop_requested:
            controller.close()
            raise StopRequested(controller.get_stop_message())
        if isinstance(data, dict) and "_event_index" not in data:
            data["_event_index"] = idx
        wait = t - last
        if wait > 0:
            if not sleep_with_controls(wait, controller):
                controller.close()
                raise StopRequested(controller.get_stop_message())
        last = t
        controller.poll_keypress()
        controller.wait_if_paused()
        if controller.stop_requested:
            controller.close()
            raise StopRequested(controller.get_stop_message())
        if handle_custom_event(kind, data, controller):
            continue
        if kind == 'move':
            controller.set_locked_mouse_position(data['x'], data['y'])
            m.position = (data['x'], data['y'])
        elif kind == 'click':
            controller.set_locked_mouse_position(data['x'], data['y'])
            m.position = (data['x'], data['y'])
            btn = _parse_button(data['button'])
            if data['pressed']:
                m.press(btn)
            else:
                m.release(btn)
        elif kind == 'scroll':
            controller.set_locked_mouse_position(data['x'], data['y'])
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





