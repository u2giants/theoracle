"""Native reply strings per employee language (plan step 2.1).

English and Simplified Chinese are written natively here — never machine
translated at send time — so operational instructions ("say done", "skip")
stay unambiguous in both languages.
"""

from __future__ import annotations

from dataclasses import dataclass

from brain.lang import detect_language


@dataclass(frozen=True)
class Strings:
    """Every employee-facing bot string in one language."""

    lang: str
    reply_intro: str
    reply_intro_short: str
    reply_ack: str
    reply_done: str
    reply_nothing_open: str
    reply_stopped: str
    reply_skipped: str
    reply_answered: str
    thread_followup: str
    message_template: str
    profile_question: str
    profile_thanks: str
    profile_thanks_raw: str
    reply_keep_going: str


_EN = Strings(
    lang="en",
    reply_intro=(
        "Hi, I'm The Oracle. I learn how POP Creations works from the people who do "
        "the work. Tell me about something you handle (who you get it from, what "
        "you do, who you pass it to) and I'll add it to the Company Map."
    ),
    reply_intro_short=(
        "Hi, I'm The Oracle. I learn how POP Creations works from the people who do "
        "the work and add it to the Company Map."
    ),
    reply_ack="Got it — keep going, or say done.",
    reply_done="Thanks, that's recorded. Message me any time you have more.",
    reply_nothing_open=(
        "There is nothing open to finish. Tell me how something works and I'll record it."
    ),
    reply_stopped=(
        "Got it, The Oracle will not send you more questions. "
        "Ask an admin to turn them back on any time."
    ),
    reply_skipped="No problem, skipped.",
    reply_answered="Thanks, that's recorded.",
    thread_followup="Got it. {question} (Or say done.)",
    message_template=(
        "Quick question from The Oracle (reply in one or two sentences, or 'skip'; "
        "reply 'stop' to pause these): {question}"
    ),
    profile_question=(
        "First, so I know who I'm talking to: what department are you in, "
        "and what's your job title?"
    ),
    profile_thanks=(
        "Thanks, noted: {title}, {department}. Now tell me about something you handle "
        "(who you get it from, what you do, who you pass it to)."
    ),
    profile_thanks_raw=(
        "Thanks, noted. Now tell me about something you handle "
        "(who you get it from, what you do, who you pass it to)."
    ),
    reply_keep_going="Got it, keep going any time.",
)

_ZH = Strings(
    lang="zh-CN",
    reply_intro=(
        "你好，我是 The Oracle。我向负责具体工作的同事了解 POP Creations 的运作方式。"
        "请告诉我你负责的事情（谁交给你的、你做什么、你再交给谁），我会把它加进公司地图。"
    ),
    reply_intro_short=(
        "你好，我是 The Oracle。我向负责具体工作的同事了解 POP Creations 的运作方式，"
        "并把它加进公司地图。"
    ),
    reply_ack="收到——继续说，或者说「完成」。",
    reply_done="谢谢，已记录。随时再告诉我更多。",
    reply_nothing_open="现在没有待完成的对话。告诉我某件事是怎么运作的，我会记录下来。",
    reply_stopped="好的，The Oracle 不会再向你提问。想重新开启，随时让管理员打开。",
    reply_skipped="没问题，已跳过。",
    reply_answered="谢谢，已记录。",
    thread_followup="收到。{question}（或者说「完成」。）",
    message_template=(
        "The Oracle 的一个小问题（用一两句话回答，或者「跳过」；"
        "回复「停止」可暂停提问）：{question}"
    ),
    profile_question="先介绍一下你自己，我才知道在跟谁聊：你在哪个部门，职位是什么？",
    profile_thanks=(
        "谢谢，已记下：{title}，{department}。"
        "现在告诉我你负责的事情（谁交给你的、你做什么、你再交给谁）。"
    ),
    profile_thanks_raw=(
        "谢谢，已记下。现在告诉我你负责的事情（谁交给你的、你做什么、你再交给谁）。"
    ),
    reply_keep_going="好的，随时继续。",
)


def strings(lang: str) -> Strings:
    """The string set for ``lang``; anything but ``zh-CN`` is English."""
    return _ZH if lang == "zh-CN" else _EN


def reply_language(locale: str | None, text: str = "") -> str:
    """``zh-CN`` locale wins; otherwise a Chinese message implies Chinese."""
    if (locale or "").strip() == "zh-CN":
        return "zh-CN"
    return "zh-CN" if detect_language(text) == "zh" else "en"
