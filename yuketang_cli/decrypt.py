# -*- coding: utf-8 -*-
"""雨课堂字体混淆解密。

逻辑与原 decrypt_problem.py 相同，仅改为通过统一 Session 下载字体、
并把 mapping_file.json 作为包内数据读取。
"""

import hashlib
import json
import re
import warnings
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from fontTools.ttLib import TTFont

MAPPING_FILE = Path(__file__).with_name("mapping_file.json")

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


class Decryptor:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def hash_glyph_commands(commands):
        command_str = json.dumps(commands, sort_keys=True)
        return hashlib.sha1(command_str.encode()).hexdigest()

    def decrypt_font(self, obfuscated_font_path, mapping_file_path=None):
        font_res = self.session.get(obfuscated_font_path)
        obfuscated_font = TTFont(BytesIO(font_res.content))

        cmap = obfuscated_font.getBestCmap()
        glyph_unicodes = {}
        for code, name in cmap.items():
            glyph_unicodes.setdefault(name, []).append(code)

        with open(mapping_file_path or MAPPING_FILE, "r", encoding="utf-8") as handle:
            original_glyph_to_uni = json.load(handle)

        obfuscated_to_original = {}
        for glyph_name in obfuscated_font.getGlyphOrder():
            unicodes = glyph_unicodes.get(glyph_name, [])
            if not unicodes:
                continue
            unicode_t = unicodes[0]

            glyph = obfuscated_font["glyf"][glyph_name]
            if glyph.numberOfContours > 0:
                commands = [f"CONTOUR_END:{glyph.endPtsOfContours}", f"COORDS:{glyph.coordinates}"]
            elif glyph.isComposite():
                components = [
                    f"{comp.glyphName}({comp.x},{comp.y})" for comp in glyph.components
                ]
                commands = ["COMPOSITE"] + components
            else:
                commands = []

            glyph_hash = self.hash_glyph_commands(commands)
            if glyph_hash in original_glyph_to_uni:
                obfuscated_to_original[unicode_t] = original_glyph_to_uni[glyph_hash]

        return obfuscated_to_original

    def get_encrypt_string(self, raw_json, ttf_url):
        decryption_map = self.decrypt_font(ttf_url)
        data = json.loads(raw_json)

        def replace_encrypted_text(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    obj[key] = replace_encrypted_text(value)
            elif isinstance(obj, list):
                for index in range(len(obj)):
                    obj[index] = replace_encrypted_text(obj[index])
            elif isinstance(obj, str):

                def decrypt_match(match):
                    encrypted_str = match.group(1)
                    decrypted_chars = [
                        chr(decryption_map.get(ord(char), ord(char))) for char in encrypted_str
                    ]
                    return "".join(decrypted_chars)

                obj = re.sub(
                    r'<span class="xuetangx-com-encrypted-font">(.*?)</span>',
                    decrypt_match,
                    obj,
                )
            return obj

        modified_data = replace_encrypted_text(data)
        return json.dumps(format_string(modified_data), ensure_ascii=False)


def clean_string(text):
    if not isinstance(text, str):
        return text
    soup = BeautifulSoup(text, "html.parser")
    cleaned = soup.get_text(separator=" ", strip=True)
    cleaned = cleaned.replace("\n", " ").replace("\r", "")
    return " ".join(cleaned.split())


def format_string(obj):
    if isinstance(obj, dict):
        return {key: format_string(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [format_string(elem) for elem in obj]
    if isinstance(obj, str):
        return clean_string(obj)
    return obj
