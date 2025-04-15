#!/usr/bin/env python3
import re
import ipaddress
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, ttk
import requests
from bs4 import BeautifulSoup
import pandas as pd
import textwrap
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os
import threading

##########################
# 文本提取与IP/URL提取功能
##########################
def clean_result(item):
    """
    清理提取结果，去除尾部可能多余的符号
    """
    return item.rstrip('}"，,').strip()

def extract_urls(text):
    """
    提取文本中所有 URL 信息：
     - 已带协议的 URL（http:// 或 https://）；
     - 带有 IP 地址和端口信息（如 prot:80 或 port:80）构造成 http://ip:port；
     - 未带协议的域名（如 www.xxx.com），自动补全为 https://
    """
    extracted = set()
    
    
    url_pattern = re.compile(r'(https?://[^\s，、,]+)')
    for url in url_pattern.findall(text):
        url = clean_result(url)
        extracted.add(url)
    
    
    ip_pattern = re.compile(r'(?:(?<!\d))(\d{1,3}(?:\.\d{1,3}){3})(?!\d)')
    for match in re.finditer(ip_pattern, text):
        ip = match.group(1)
        following_text = text[match.end():match.end()+20]
        port_match = re.search(r'(?:prot|port)[:：]\s*(\d+)', following_text, re.IGNORECASE)
        if port_match:
            port = port_match.group(1)
            url = "http://{}:{}".format(ip, port)
        else:
            url = "http://{}".format(ip)
        url = clean_result(url)
        extracted.add(url)
        
   
    domain_pattern = re.compile(
        r'(?<!://)(?<![0-9\.])((?:www\.)?[a-zA-Z0-9-]+\.(?:com|net|org|cn|cc|io|gov|edu)(?:\.[a-zA-Z]{2,})?)'
    )
    for domain in domain_pattern.findall(text):
        domain = clean_result(domain)
        extracted.add("https://{}".format(domain))
        
    return list(extracted)

def extract_all_ips(text):
    """
    提取文本中的所有合法 IPv4 地址
    """
    pattern = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3})')
    candidates = pattern.findall(text)
    valid_ips = set()
    for ip in candidates:
        try:
            candidate_ip = ipaddress.IPv4Address(ip)
            valid_ips.add(str(candidate_ip))
        except Exception:
            continue
    return list(valid_ips)


class ModeSelectionDialog(simpledialog.Dialog):
    """
    自定义对话框，使用滑块选择提取模式：
      - 0 对应 IP，1 对应 URL
    """
    def body(self, master):
        tk.Label(master, text="请选择提取模式：").pack(pady=5)
        self.scale = tk.Scale(master, from_=0, to=1, orient=tk.HORIZONTAL, resolution=1, length=200, tickinterval=1)
        tk.Label(master, text="0：IP    1：URL").pack()
        self.scale.set(1)  
        self.scale.pack(padx=10, pady=5)
        return self.scale

    def apply(self):
        value = self.scale.get()
        self.result = "ip" if value == 0 else "url"


def check_url_status(url):
    """
    检测 URL 存活状态，返回 (状态码, 网页标题)
    """
    try:
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = session.get(url, timeout=10, verify=False, headers=headers)
        response.encoding = response.apparent_encoding
        status_code = response.status_code
        soup = BeautifulSoup(response.text, 'html.parser')
        title = soup.title.string if soup.title and soup.title.string else 'null'
        return status_code, title
    except requests.exceptions.RequestException as e:
        return 'Error', str(e)

def wrap_text(text, width=80):
    """
    自动换行处理文本
    """
    if text is None:
        return 'null'
    return "\n".join(textwrap.wrap(text, width))

def check_urls_list(urls, progress_callback):
    """
    对传入的 URL 列表进行存活检测，并生成检测结果 DataFrame
    """
    results = []
    total = len(urls)
    for index, url in enumerate(urls):
        
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        status_code, title = check_url_status(url)
        results.append([url, status_code, wrap_text(title)])
        progress_callback(index + 1, total)
    df = pd.DataFrame(results, columns=['URL', 'Status Code', 'Title'])
    return df

def get_unique_filename(base_filename):
    """
    自动生成不重复的文件名（用于保存 Excel 结果）
    """
    i = 1
    file_name, file_extension = os.path.splitext(base_filename)
    unique_filename = base_filename
    while os.path.exists(unique_filename):
        unique_filename = f"{file_name}_{i}{file_extension}"
        i += 1
    return unique_filename

def save_results_to_excel(df):
    """
    弹窗选择保存目录，将结果 DataFrame 保存为 Excel 文件
    """
    output_directory = filedialog.askdirectory(title="选择保存目录")
    if not output_directory:
        messagebox.showerror("错误", "未选择目录，操作取消。")
        return
    base_filename = os.path.join(output_directory, "检测结果.xlsx")
    unique_filename = get_unique_filename(base_filename)
    try:
        df.to_excel(unique_filename, index=False, engine='openpyxl')
        messagebox.showinfo("成功", f"结果已保存到: {unique_filename}")
    except Exception as e:
        messagebox.showerror("错误", f"保存文件失败: {str(e)}")

def run_url_check_gui(urls, parent):
    """
    新建一个窗口，显示 URL 检测进度，检测完成后保存结果到 Excel
    """
    progress_window = tk.Toplevel(parent)
    progress_window.title("URL 存活检测")
    tk.Label(progress_window, text="正在检测 URL 存活状态...").pack(pady=10)
    
    progress_bar = ttk.Progressbar(progress_window, length=400, mode='determinate')
    progress_bar.pack(pady=10)
    progress_percentage = tk.Label(progress_window, text="0%")
    progress_percentage.pack(pady=5)

    def update_progress(current, total):
        progress_bar["value"] = (current / total) * 100
        progress_percentage.config(text=f"{int((current / total) * 100)}%")
        progress_window.update_idletasks()

    def run_check():
        try:
            df = check_urls_list(urls, update_progress)
            progress_window.destroy()  
            save_results_to_excel(df)
        except Exception as e:
            messagebox.showerror("错误", f"检测过程中发生异常: {str(e)}")
            progress_window.destroy()

    threading.Thread(target=run_check, daemon=True).start()


def main():
    root = tk.Tk()
    root.withdraw()

    
    input_filepath = filedialog.askopenfilename(
        title="请选择包含原始文本的输入文件",
        filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
    )
    if not input_filepath:
        messagebox.showinfo("提示", "未选择输入文件，程序退出。")
        return

    try:
        with open(input_filepath, "r", encoding="utf-8") as infile:
            input_text = infile.read()
    except Exception as e:
        messagebox.showerror("错误", f"读取文件失败: {str(e)}")
        return

    
    mode_dialog = ModeSelectionDialog(root, title="选择提取模式")
    if mode_dialog.result is None:
        messagebox.showinfo("提示", "未选择提取模式，程序退出。")
        return
    mode = mode_dialog.result

    if mode == "ip":
        
        results = extract_all_ips(input_text)
        output_filepath = filedialog.asksaveasfilename(
            title="请选择输出文件保存位置",
            defaultextension=".txt",
            initialfile="complete.txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not output_filepath:
            output_filepath = "complete.txt"
        try:
            with open(output_filepath, "w", encoding="utf-8") as outfile:
                for item in results:
                    outfile.write(item + "\n")
            messagebox.showinfo("完成", f"提取结果已保存到：{output_filepath}")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件失败: {str(e)}")
    else:
       
        urls = extract_urls(input_text)
        if not urls:
            messagebox.showinfo("提示", "未提取到任何 URL！")
            return

        
        if messagebox.askyesno("URL 存活检测", "是否进行 URL 存活检测？\n选择“是”将检测 URL 存活状态并保存检测结果为 Excel，选择“否”直接保存提取的 URL。"):
            
            root.deiconify()  
            run_url_check_gui(urls, root)
            root.mainloop()  
        else:
            
            output_filepath = filedialog.asksaveasfilename(
                title="请选择输出文件保存位置",
                defaultextension=".txt",
                initialfile="complete.txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
            )
            if not output_filepath:
                output_filepath = "complete.txt"
            try:
                with open(output_filepath, "w", encoding="utf-8") as outfile:
                    for item in urls:
                        outfile.write(item + "\n")
                messagebox.showinfo("完成", f"提取结果已保存到：{output_filepath}")
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {str(e)}")

if __name__ == "__main__":
    main()
