"""Large, keyboard-accessible day counters instead of native tiny spinner arrows."""
from nicegui import ui


def day_stepper(label, value, *, minimum=0, maximum=370):
    with ui.row().classes("ds-day-stepper w-full items-center no-wrap") as row:
        field = ui.number(label, value=value, min=minimum, max=maximum, step=1).props("outlined").classes("grow min-w-0 ds-stepper-input")
        def change(amount):
            try:
                current = int(field.value or 0)
            except (ValueError, TypeError):
                current = 0
            field.value = max(minimum, min(maximum, current + amount))
        minus = ui.button(icon="remove", on_click=lambda: change(-1)).props('outline round aria-label="Ubrat den"').mark("day-minus")
        plus = ui.button(icon="add", on_click=lambda: change(1)).props('outline round aria-label="Přidat den"').mark("day-plus")
        def update():
            try:
                current = float(field.value or 0)
                minus.set_enabled(current > minimum)
                plus.set_enabled(current < maximum)
            except (ValueError, TypeError):
                minus.enable()
                plus.enable()
        field.on_value_change(lambda _event: update())
        update()
    field.stepper_row = row
    return field
