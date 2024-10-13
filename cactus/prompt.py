from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.shortcuts import clear
from prompt_toolkit.formatted_text import FormattedText
from loguru import logger
import sys

def display_clusters(clusters):
    n_hunks = sum([len(cluster['hunk_indices']) for cluster in clusters])
    message = f"Grouped {n_hunks} hunks into {len(clusters)} commits:\n"
    for ix, cluster in enumerate(clusters):
        message += f"- Commit {ix} ({len(cluster['hunk_indices'])} hunks): {cluster['message']}\n"
    logger.success(message)

def handle_user_input(prompt_data, clusters_n, get_clusters_func):
    choices = [
        ('accept', 'Accept', 'c'),
        ('regenerate', 'Regenerate', 'r'),
        ('increase', 'Increase #', 'i'),
        ('decrease', 'Decrease #', 'd'),
        ('quit', 'Quit', 'q'),
    ]

    style = Style.from_dict({
        'bottom-toolbar': 'bg:#444444 #ffffff',
        'selected': 'bg:#ffffff #000000 bold',  # Inverted style for selected
        'unselected': 'bg:#444444 #ffffff',     # Normal style for unselected
    })

    kb = KeyBindings()

    selected_index = [0]
    feedback = ['']

    @kb.add('left')
    def _(event):
        selected_index[0] = (selected_index[0] - 1) % len(choices)
        event.app.invalidate()

    @kb.add('right')
    def _(event):
        selected_index[0] = (selected_index[0] + 1) % len(choices)
        event.app.invalidate()

    def get_toolbar():
        # Create a formatted text with proper styles for selected and unselected items
        toolbar_items = []
        for i, (key, name, shortcut) in enumerate(choices):
            if i == selected_index[0]:
                # Apply 'selected' style to the currently selected option
                toolbar_items.append(('class:selected', f" ({shortcut}) {name} "))
            else:
                # Apply 'unselected' style to the non-selected options
                toolbar_items.append(('class:unselected', f" ({shortcut}) {name} "))
        return FormattedText(toolbar_items)

    def handle_action(key, event):
        if key == 'accept':
            feedback[0] = 'Accepting...'
        elif key == 'regenerate':
            feedback[0] = 'Regenerating commits...'
        elif key == 'increase':
            feedback[0] = 'Increasing number of commits...'
        elif key == 'decrease':
            feedback[0] = 'Decreasing number of commits...'
        elif key == 'quit':
            feedback[0] = 'Aborting...'
        event.app.exit(result=key)

    for key, name, shortcut in choices:
        @kb.add(shortcut)
        def _(event, key=key):
            handle_action(key, event)

    @kb.add('enter')
    def _(event):
        key = choices[selected_index[0]][0]
        handle_action(key, event)

    # Prevent user input
    @kb.add('<any>')
    def _(event):
        pass

    clusters = get_clusters_func(prompt_data, clusters_n=clusters_n)
    display_clusters(clusters)

    result = prompt('',
                    key_bindings=kb,
                    bottom_toolbar=get_toolbar,
                    style=style,
                    )

    print(feedback[0])

    if result == 'accept':
        pass  # Proceed to return clusters
    elif result == 'regenerate':
        return handle_user_input(prompt_data, clusters_n, get_clusters_func)
    elif result == 'increase':
        return handle_user_input(prompt_data, len(clusters) + 1 if clusters_n is None else clusters_n + 1, get_clusters_func)
    elif result == 'decrease':
        clusters_n = len(clusters) if clusters_n is None else clusters_n
        if clusters_n <= 1:
            logger.warning("Cannot decrease further. Minimum number of clusters is 1.")
        else:
            clusters_n -= 1
        return handle_user_input(prompt_data, clusters_n, get_clusters_func)
    elif result == 'quit':
        logger.error("Aborted by user.")
        sys.exit(1)

    return clusters
