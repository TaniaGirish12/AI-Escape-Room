"""Shared look and small HTML building blocks used by both versions.

Only presentation lives here. Game logic stays in version1/ and version2/.
All text placed into HTML is escaped, so LLM output is never rendered as HTML.
"""

import base64
from html import escape
from pathlib import Path

import streamlit as st

UI_DIR = Path(__file__).resolve().parent

OBJECT_ICONS = {
    "desk": "🪔", "drawer": "🗄️", "bookshelf": "📚", "painting": "🖼️",
    "cabinet": "🪟", "clock": "🕰️", "door": "🚪",
}
ITEM_ICONS = {"brass_key": "🗝️", "uv_flashlight": "🔦"}

STATUS_LABELS = {
    "locked": "🔒 Locked", "open": "🔓 Open", "revealed": "✨ Revealed",
    "examined": "Examined", "unexplored": "Unexplored", "unknown": "Unknown",
}

GAME_MASTER_AVATAR = "🕯️"
PLAYER_AVATAR = "🧭"


def title_case(text: str) -> str:
    """Capitalise the first letter only, so "UV flashlight" stays "UV flashlight"."""
    return text[:1].upper() + text[1:]


def apply_theme() -> None:
    css = (UI_DIR / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def hero(title: str, subtitle: str, version_label: str) -> None:
    svg = base64.b64encode((UI_DIR / "library_banner.svg").read_bytes()).decode()
    st.markdown(
        f'<div class="hero"><img alt="Illustration of the library: bookshelf, painting, desk lamp, '
        f'clock, glass cabinet and door" src="data:image/svg+xml;base64,{svg}"/>'
        f'<div class="hero-text"><div class="hero-title">{escape(title)}'
        f'<span class="version-pill">{escape(version_label)}</span></div>'
        f'<div class="hero-sub">{escape(subtitle)}</div></div></div>',
        unsafe_allow_html=True,
    )


def chip(status: str) -> str:
    return f'<span class="chip {escape(status)}">{escape(STATUS_LABELS.get(status, status))}</span>'


def object_header(object_id: str, name: str, status: str) -> str:
    icon = OBJECT_ICONS.get(object_id, "•")
    return (f'<div class="obj-head"><span class="obj-icon">{icon}</span><div>'
            f'<div class="obj-name">{escape(title_case(name))}</div>'
            f'<div class="obj-sub">{chip(status)}</div></div></div>')


def side_label(text: str) -> None:
    st.markdown(f'<div class="side-label">{escape(text)}</div>', unsafe_allow_html=True)


def role_marker(role: str) -> None:
    """Invisible marker so the stylesheet can tell player and Game Master messages apart."""
    css_class = "who-player" if role == "user" else "who-gm"
    st.markdown(f'<span class="{css_class}"></span>', unsafe_allow_html=True)


def victory_card(moves: int, extra_stats: dict[str, int] | None = None) -> None:
    stats = {"Moves": moves, **(extra_stats or {})}
    cells = "".join(f'<div class="stat"><div class="n">{value}</div><div class="l">{escape(label)}</div></div>'
                    for label, value in stats.items())
    st.markdown(
        '<div class="victory"><div class="big">You escaped!</div>'
        '<div class="lead">Cool night air rushes in as the heavy oak door swings open.</div>'
        f'<div class="stats">{cells}</div></div>',
        unsafe_allow_html=True,
    )
