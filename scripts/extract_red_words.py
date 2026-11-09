#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 PDF 教材中提取红色字体(0xFF0000)的单词释义。

用法:
    python3 extract_red_words.py <pdf路径> <输出xlsx路径>

流程:
1. 收集所有 0xFF0000 的 span
2. 按页 + 行(y坐标)合并同一行的 span，得到完整文本行
3. 用 / 分割每个行，得到若干释义片段
4. 用正则匹配 "单词 词性.中文" 模式，输出最终 Excel（A=words, B=translation）

依赖: PyMuPDF (fitz), openpyxl
"""
import fitz
import re
import sys

PURE_RED = 0xFF0000

def is_pure_red(color_int):
    return color_int == PURE_RED

def collect_red_lines(pdf_path):
    """按页+行合并红色span，返回每页的红色文本行列表"""
    doc = fitz.open(pdf_path)
    pages_lines = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        d = page.get_text("dict")
        spans = []
        for block in d.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    color = span.get("color", 0)
                    if text and is_pure_red(color):
                        bbox = span.get("bbox")
                        spans.append({
                            "text": text,
                            "x0": bbox[0],
                            "y0": bbox[1],
                            "x1": bbox[2],
                            "y1": bbox[3],
                        })
        spans.sort(key=lambda s: (s["y0"], s["x0"]))
        lines = []
        cur_line = []
        cur_y = None
        for s in spans:
            if cur_y is None or abs(s["y0"] - cur_y) <= 3:
                cur_line.append(s)
                cur_y = s["y0"] if cur_y is None else cur_y
            else:
                lines.append(cur_line)
                cur_line = [s]
                cur_y = s["y0"]
        if cur_line:
            lines.append(cur_line)
        page_lines = []
        for ln in lines:
            ln.sort(key=lambda s: s["x0"])
            text = "".join(s["text"] for s in ln)
            page_lines.append(text)
        pages_lines.append(page_lines)
    doc.close()
    return pages_lines

POS_PATTERN = (
    r"(?:(?:prep|conj|abbr|pron|adj|adv|aux|num|int|art|vt|vi|n|v)\."
    r"|(?:prep|conj|abbr|pron|adj|adv|aux|num|int|art|vt|vi|n|v)(?=[\u4e00-\u9fff\s<])"
    r"|<[^>]+?>)"
)
ENTRY_RE = re.compile(
    r"^\s*(.+?)\s+(" + POS_PATTERN + r")\s*(.+)$"
)
ENTRY_NO_POS_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z\s'\-]+?)\s+([\u4e00-\u9fff].+)$"
)
ENTRY_COLON_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z\s'\-\.]*?)\s*[:：]\s*([\u4e00-\u9fff].+)$"
)

def has_chinese(s):
    return bool(re.search(r"[\u4e00-\u9fff]", s))

def clean_translation(text):
    text = text.replace("<", "「").replace(">", "」")
    text = text.replace("〈", "「").replace("〉", "」")
    text = text.replace("[", "「").replace("]", "」")
    return text

def ends_with_pos(line):
    return bool(re.search(r"\b(?:n|v|vt|vi|adj|adv|prep|conj|art|pron|num|int|abbr|aux)\.$", line.strip()))

def has_unclosed_paren(s):
    return (s.count("(") + s.count("（")) > (s.count(")") + s.count("）"))

def starts_with_pos(line):
    return bool(re.match(r"^\s*(?:n|v|vt|vi|adj|adv|prep|conj|art|pron|num|int|abbr|aux)\.", line.strip()))

def starts_with_chinese(line):
    s = line.lstrip()
    return bool(s) and bool(re.match(r"[\u4e00-\u9fff]", s))

def ends_with_english(line):
    s = line.rstrip()
    return bool(s) and bool(re.search(r"[A-Za-z]$", s))

def starts_with_english(line):
    s = line.lstrip()
    return bool(s) and bool(re.match(r"[A-Za-z]", s))

def contains_pos_marker(line):
    stripped = re.sub(r"[\(\（][^\)\）]*[\)\）]", "", line)
    return bool(re.search(r"(?<![A-Za-z])(?:prep|conj|abbr|pron|adj|adv|aux|num|int|art|vt|vi|n|v)\.", stripped)
                or re.search(r"(?<![A-Za-z])(?:prep|conj|abbr|pron|adj|adv|aux|num|int|art|vt|vi|n|v)(?=[\u4e00-\u9fff<])", stripped)
                or re.search(r"<[^>]+?>|〈[^〉]+?〉", stripped))

def merge_cross_page_lines(page_lines):
    flat = []
    for i, lines in enumerate(page_lines, 1):
        for ln in lines:
            flat.append((i, ln))
    merged = []
    i = 0
    while i < len(flat):
        page, line = flat[i]
        while i + 1 < len(flat):
            nxt = flat[i + 1][1]
            nxt_s = nxt.strip()
            should_merge = False
            if ends_with_pos(line) or has_unclosed_paren(line):
                should_merge = True
            elif starts_with_pos(nxt_s) and not ends_with_pos(line):
                should_merge = True
            elif starts_with_chinese(nxt_s):
                should_merge = True
            elif nxt_s.startswith("("):
                should_merge = True
            elif ends_with_english(line) and starts_with_english(nxt_s) and not contains_pos_marker(nxt_s):
                should_merge = True
            if not should_merge:
                break
            if starts_with_chinese(nxt_s):
                line = line + nxt_s
            elif starts_with_pos(nxt_s):
                line = line + " " + nxt_s
            elif starts_with_english(nxt_s):
                line = line + " " + nxt_s
            else:
                line = line + nxt_s
            i += 1
        merged.append((page, line))
        i += 1
    return merged

def parse_entries_from_line(line):
    results = []
    parts = line.split("/")
    for part in parts:
        part = part.strip()
        if not part or not has_chinese(part):
            continue
        part = part.replace("\u2019", "'")
        part = re.sub(r"(?<!\s)<", " <", part)
        part = re.sub(r"(?<![A-Za-z])([A-Za-z]{3,})((?:n|v|vt|vi|adj|adv|prep|conj|art|pron|num|int|abbr|aux)\.)", r"\1 \2", part)
        m = ENTRY_RE.match(part)
        if m:
            word = m.group(1).strip()
            pos = m.group(2).strip()
            meaning = m.group(3).strip()
            if pos and not pos.startswith("<") and not pos.endswith("."):
                pos = pos + "."
            results.append((word, f"{pos}{meaning}"))
            continue
        m2 = ENTRY_NO_POS_RE.match(part)
        if m2:
            results.append((m2.group(1).strip(), m2.group(2).strip()))
            continue
        m3 = ENTRY_COLON_RE.match(part)
        if m3:
            results.append((m3.group(1).strip(), m3.group(2).strip()))
            continue
        results.append(("[未解析]", part))
    return results

def main():
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill

    if len(sys.argv) < 3:
        print("用法: python3 extract_red_words.py <pdf路径> <输出xlsx路径>")
        sys.exit(1)
    pdf_path = sys.argv[1]
    out_path = sys.argv[2]

    pages_lines = collect_red_lines(pdf_path)
    merged_lines = merge_cross_page_lines(pages_lines)

    all_entries = []
    for page, ln in merged_lines:
        all_entries.extend(parse_entries_from_line(ln))

    failed = [e for e in all_entries if e[0] == "[未解析]"]

    wb = Workbook()
    ws = wb.active
    ws.title = "words"
    ws.append(["words", "translation"])
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col_idx in range(1, 3):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for word, trans in all_entries:
        ws.append([word, clean_translation(trans)])
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 40
    wb.save(out_path)

    print(f"已写入 {out_path}，共 {len(all_entries)} 条（其中未解析 {len(failed)} 条，见下）")
    for word, trans in failed:
        print(f"  [未解析] {trans[:80]}")

if __name__ == "__main__":
    main()
