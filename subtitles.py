# /usr/bin/env python3

import csv
import itertools
import re
import textwrap
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import islice
from pathlib import Path
from typing import Dict, Generator, List, Set, Tuple

MAX_LINE_LENGTH: int = 37  # formerly 38
LINES_ON_SCREEN: int = 24

# These are for aligning on the right column:
# X_POS = 380
Y_POS = 15  # formerly 25

# While these are for aligning in the middle-ish
X_POS = 170
# Y_POS = 100


NAME_REPLACEMENTS: Dict[str, str] = {
    # Mapping from original name to name that will show up in the generated
    # subtitles.
    # Currently blank, as it has been anonymized from the original file.
}


def rgb_to_ass_tag(r, g, b) -> str:
    r_hex = hex(r)[2:]
    g_hex = hex(g)[2:]
    b_hex = hex(b)[2:]
    return f"{{\\c&H{b_hex}{g_hex}{r_hex}&}}"


ELECTROLATE = rgb_to_ass_tag(26, 187, 243)
SCUD = rgb_to_ass_tag(241, 196, 15)
MOXIE = rgb_to_ass_tag(255, 226, 227)
MODS = rgb_to_ass_tag(32, 95, 112)
PRISONER = rgb_to_ass_tag(46, 192, 87)
TMH = rgb_to_ass_tag(113, 82, 182)
MINITRUE = rgb_to_ass_tag(43, 139, 76)

NAME_COLORS: Dict[str, str] = {
    "BattleToad": ELECTROLATE,
    "bDwS": ELECTROLATE,
    "CantHandleMyHandle": ELECTROLATE,
    "Chud Droopy": MODS,
    "Clone": ELECTROLATE,
    "Crunchyeater": PRISONER,
    "dasty": ELECTROLATE,
    "Don Haußettler": ELECTROLATE,
    "duk": MINITRUE,
    "Gym Slow": PRISONER,
    "Jammho": ELECTROLATE,
    "KitKat": ELECTROLATE,
    "Lamb's Ear": PRISONER,
    "Lordy": MODS,
    "Mermaid": ELECTROLATE,
    "MF": MOXIE,
    "Poopenheimer": ELECTROLATE,
    "Quate": PRISONER,
    "sling": SCUD,
    "spaghetti squash": ELECTROLATE,
    "Spicy Deluxe": ELECTROLATE,
    "teratoma jones": ELECTROLATE,
    "tmh": TMH,
    "Toner Martini": ELECTROLATE,
}


@dataclass
class Message:
    sent_time: str
    text: str


def common_line_beginning(begin_time: str, end_time: str) -> str:
    return (
        f"Dialogue: "
        f"0,{begin_time},{end_time},"
        f"Chat Replay,,0,0,0,,{{\\pos({X_POS},{Y_POS})}}"
    )


def format_all_but_bottom(
    messages: List[Message], begin_time: str, end_time: str
) -> str:
    full_text = "\\N".join(message.text for message in messages)
    return common_line_beginning(begin_time, end_time) + full_text


def format_faded_messages(
    messages: List[Message], begin_time: str, end_time: str
) -> List[str]:
    output = []
    for i, message in enumerate(messages):
        index_from_bottom = len(messages) - i
        output.append(
            common_line_beginning(begin_time, end_time)
            + "{\\fad(1000,0)}"
            # The space being BEFORE the \N here is very important,
            # for some *.ass format reason I don't understand.
            # If it's AFTER, then each line is half the height (?!?!).
            + (" \\N" * (LINES_ON_SCREEN - index_from_bottom))
            + message.text
        )
    return output


def get_lines_in_file() -> List[str]:
    # This _should_ be using csvparser, and causes bugs if any of the
    # lines contain newlines, but I just manually fixed all those...
    lines_including_header = Path("talkie_v2.csv").read_text().split("\n")
    return lines_including_header[1:]


CRUMBLES_SNIPS = [
    ("00:05:20.00", "00:05:54.00"),  # cut poopenheimer tuning
    ("00:25:34.00", "00:25:39.90"),  # cut door swinging
    ("00:39:01.90", "00:39:11.00"),  # cut awkward pause
    ("00:39:06.00", "00:39:50.00"),  # cut more awkward pause
    ("00:40:12.40", "00:40:22.20"),  # cut to sunnyvale hate
    ("00:40:32.40", "00:41:43.70"),  # cut to the mulkmen
    ("00:57:17.60", "00:57:37.50"),  # cut to mermaid
    ("00:58:00.00", "00:58:19.90"),  # cut dead air
    ("01:21:08.70", "01:21:20.00"),  # cut out...
    ("01:21:15.00", "01:22:49.00"),  # cut out don's mic check
]


def convert_to_datetime(decimal_timestamp: str) -> datetime:
    return datetime.strptime(decimal_timestamp, "%H:%M:%S.%f")


def convert_crumbles_to_absolute() -> List[Tuple[datetime, datetime, timedelta]]:
    real_snips = []
    total_snipped = timedelta(seconds=0)
    for snip_begin, snip_end in CRUMBLES_SNIPS:
        snip_begin_time = convert_to_datetime(snip_begin)
        snip_end_time = convert_to_datetime(snip_end)

        real_snip_begin = snip_begin_time + total_snipped
        real_snip_end = snip_end_time + total_snipped

        real_snips.append((real_snip_begin, real_snip_end, total_snipped))
        total_snipped += snip_end_time - snip_begin_time

    return real_snips


def convert_message_timestamp_to_subtitle_time(timestamp: str) -> str:
    timestamp_as_date = datetime.strptime(timestamp, "%H:%M:%S")

    # 00:04:28.00 in Crumbles's video equals a message with timestamp
    # 04:08:20.00.
    # This means we need to subtract this amount from
    # each message's timestamp to sync them up:
    timestamp_as_date -= timedelta(hours=4, minutes=3, seconds=52)
    # timestamp_as_date -= timedelta(hours=5, minutes=55, seconds=33)

    # Then, we need to flatten the messages that occurred during the snipped
    # sections of audio.

    absolutes = convert_crumbles_to_absolute()
    held_within = [
        (begin, to_snip)
        for (begin, end, to_snip) in absolutes
        if begin <= timestamp_as_date <= end
    ]
    if held_within:
        timestamp_as_date = held_within[0][0] - held_within[0][1]
    else:
        # beginning, in between, or end
        if timestamp_as_date < absolutes[0][0]:
            # beginning:
            pass  # nothing to do
        elif timestamp_as_date > absolutes[-1][1]:
            # end:
            timestamp_as_date -= absolutes[-1][2]
        else:
            # somewhere in the middle... find out which slices its between
            # this is the worst code i've ever written. don't care for now
            timestamp_as_date -= absolutes[
                [
                    i
                    for i, (_, end, _) in enumerate(absolutes)
                    if end < timestamp_as_date
                ][-1]
                + 1
            ][2]

    return datetime.strftime(timestamp_as_date, "%H:%M:%S.00")


class InsaneHack(str):
    def __len__(self):
        return 2


class ReduceClaps(str):
    def __len__(self):
        return super().__len__() + super().count("👏")


def get_messages_from_line(line: str) -> List[Message]:
    [author, timestamp, quoted_text, attachment, reactions, _] = line.split(";")
    sent_time = convert_message_timestamp_to_subtitle_time(timestamp[1:-1])

    author = author[1:-1]
    author = author[: author.index("#")]
    if author in NAME_REPLACEMENTS:
        author = NAME_REPLACEMENTS[author]

    text = f"{author}: {quoted_text[1:-1]}"
    text = text.replace('""', '"')
    # Okay, here's the deal. No one sent any "]", and textwrap isn't multi-byte
    # character aware, so we replace the long clap messages people sent with
    # the sentinel "]]", then replace it back. Sorry.
    insane_hack_text = text.replace("👏", "]]")

    messages = [
        Message(sent_time=sent_time, text=content.replace("]]", "👏"))
        for content in textwrap.wrap(
            insane_hack_text, MAX_LINE_LENGTH, subsequent_indent=InsaneHack("\\h\\h")
        )
    ]
    text_white_reset = "{\\c&HFFFFFF&}"
    messages[0].text = messages[0].text.replace(
        author + ": ", NAME_COLORS[author] + author + ": " + text_white_reset
    )
    return messages


def get_messages_in_file() -> List[List[Message]]:
    total_messages: List[List[Message]] = []
    for line in get_lines_in_file():
        [_, _, quoted_text, _, _, _] = line.split(";")
        if quoted_text == '""':
            # This can happen if the person only sent a picture.
            continue
        total_messages.append(get_messages_from_line(line))
    return total_messages


def flat_window(
    seq: List[List[Message]], n: int
) -> Generator[Tuple[int, List[Message]], None, None]:
    # result = list(islice(it, n))
    # we could lose the first few elements here... there's no way around it
    result: List[Message] = []
    i = 0
    while len(result) < n:
        result += seq[i]
        i += 1
    result = result[-n:]  # bye bye :(
    yield (len(seq[i - 1]), result)

    it = iter(seq[i:])
    for elem in it:
        new_additions_length = len(elem)
        result = result[new_additions_length:] + elem
        yield (len(elem), result)


def get_output_lines() -> List[str]:
    # The output lines are just this repeating unit:
    #   [all but bottom]
    #   [bottom, with fade-in]
    # Note that at the beginning, we have zero lines, but it still holds.
    padding = [[Message(sent_time="0:00:00.00", text=" ")]] * LINES_ON_SCREEN
    padded_messages = padding + get_messages_in_file()
    windows = list(flat_window(padded_messages, LINES_ON_SCREEN))
    final_lines: List[str] = []
    # TODO: used to do +1 here to get timestamp
    for i, (length, message_chunk) in enumerate(windows):
        begin_time = message_chunk[-1].sent_time
        # end_time = message_chunk[-1].sent_time
        try:
            end_time = windows[i + 1][1][-1].sent_time  # TODO: check.
        except IndexError:
            end_time = "01:37:23.00"

        # TODO: Replace this [:-1] with a [:-length] where length is
        # the amount of lines that the bottom took.
        final_lines.append(
            format_all_but_bottom(message_chunk[:-length], begin_time, end_time)
        )
        final_lines += format_faded_messages(
            message_chunk[-length:], begin_time, end_time
        )

    return final_lines


def main():
    lines = get_output_lines()
    base = Path("subtitles_base.ass")
    out = Path("subtitles_out.ass")
    with out.open("w") as out_file:
        out_file.write(base.read_text())
        out_file.write("\n".join(lines))
    print("done")


if __name__ == "__main__":
    main()
