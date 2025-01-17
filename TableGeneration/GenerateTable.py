import json
import os
import sys
import random
import string
from PIL import Image, ImageOps, ImageFilter
from io import BytesIO
from tqdm import tqdm
import numpy as np
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import cv2
from TableGeneration.Table import Table


class GenerateTable:
    def __init__(
        self,
        output,
        ch_dict_path,
        en_dict_path,
        cell_box_type="cell",
        min_row=3,
        max_row=20,
        min_col=3,
        max_col=10,
        max_span_row_count=3,
        max_span_col_count=3,
        max_span_value=20,
        min_txt_len=2,
        max_txt_len=7,
        color_prob=0,
        cell_max_width=0,
        cell_max_height=0,
        brower="chrome",
        brower_width=1920,
        brower_height=1920,
        backgroud="gaussian_noise",
    ):
        self.output = output  # wheter to store images separately or not
        self.ch_dict_path = ch_dict_path
        self.en_dict_path = en_dict_path
        self.cell_box_type = cell_box_type  # cell: use cell location as cell box; text: use location of text in cell as cell box
        self.min_row = min_row  # minimum number of rows in a table (includes headers)
        self.max_row = max_row  # maximum number of rows in a table
        self.min_col = min_col  # minimum number of columns in a table
        self.max_col = max_col  # maximum number of columns in a table
        self.max_txt_len = max_txt_len  # maximum number of chars in a cell
        self.min_txt_len = min_txt_len  # minimum number of chars in a cell
        self.color_prob = color_prob  # color cell prob
        self.cell_max_width = cell_max_width  # max cell w
        self.cell_max_height = cell_max_height  # max cell h
        self.max_span_row_count = max_span_row_count  # max span row count
        self.max_span_col_count = max_span_col_count  # max span col count
        self.max_span_value = max_span_value  # max span value
        self.brower = brower  # brower used to generate html table
        self.brower_height = brower_height  # brower height
        self.brower_width = brower_width  # brower width
        self.backgroud = backgroud  # backgroud

        if self.brower == "chrome":
            from selenium.webdriver import Chrome as Brower
            from selenium.webdriver import ChromeOptions as Options
        else:
            from selenium.webdriver import Firefox as Brower
            from selenium.webdriver import FirefoxOptions as Options
        opts = Options()
        opts.add_argument("--headless")
        opts.add_argument("--no-sandbox")
        self.driver = Brower(options=opts)

    def gen_table_img(self, img_count):
        os.makedirs(self.output, exist_ok=True)
        f_gt = open(os.path.join(self.output, "gt.txt"), encoding="utf-8", mode="w")
        for i in tqdm(range(img_count)):
            # data_arr contains the images of generated tables and all_table_categories contains the table category of each of the table
            out = self.generate_table()
            if out is None:
                continue

            im, html_content, structure, contens, border = out
            im, contens = self.clip_white(im, contens)  # TODO : 我应该对这个地方做裁减

            # randomly select a name of length=20 for file.
            output_file_name = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=20)
            )
            output_file_name = "gen_{}_{}_{}".format(border, i, output_file_name)
            # print('{}/{}, {}'.format(i, img_count, output_file_name))

            # if the image and equivalent html is need to be stored
            os.makedirs(os.path.join(self.output, "html"), exist_ok=True)
            os.makedirs(os.path.join(self.output, "img"), exist_ok=True)

            html_save_path = os.path.join(
                self.output, "html", output_file_name + ".html"
            )
            img_save_path = os.path.join(self.output, "img", output_file_name + ".jpg")
            with open(html_save_path, encoding="utf-8", mode="w") as f:
                f.write(html_content)
            im.save(img_save_path, dpi=(600, 600))

            # 构造标注信息
            img_file_name = os.path.join("img", output_file_name + ".jpg")
            label_info = self.make_ppstructure_label(structure, contens, img_file_name)

            f_gt.write("{}\n".format(json.dumps(label_info, ensure_ascii=False)))
        # convert to PP-Structure label format
        f_gt.close()
        self.close()

    def generate_table(self):
        # 随机生成行列长度
        cols = random.randint(self.min_col, self.max_col)
        rows = random.randint(self.min_row, self.max_row)
        try:
            # initialize table class
            table = Table(
                self.ch_dict_path,
                self.en_dict_path,
                self.cell_box_type,
                rows,
                cols,
                self.min_txt_len,
                self.max_txt_len,
                self.max_span_row_count,
                self.max_span_col_count,
                self.max_span_value,
                self.color_prob,
                self.cell_max_width,
                self.cell_max_height,
            )
            # get table of rows and cols based on unlv distribution and get features of this table
            # (same row, col and cell matrices, total unique ids, html conversion of table and its category)
            id_count, html_content, structure, border = table.create()

            # convert this html code to image using selenium webdriver. Get equivalent bounding boxes
            # for each word in the table. This will generate ground truth for our problem
            im, contens = self.html_to_img(html_content, id_count)
            return im, html_content, structure, contens, border
        except KeyboardInterrupt:
            import sys

            sys.exit()
        except:
            import traceback

            traceback.print_exc()
            return None
        return None

    def make_ppstructure_label(self, structure, bboxes, img_path):
        d = {"filename": img_path, "html": {"structure": {"tokens": structure}}}
        cells = []
        for bbox in bboxes:
            text = bbox[1]
            cells.append({"tokens": list(text), "bbox": bbox[2:]})
        d["html"]["cells"] = cells
        d["gt"] = self.rebuild_html_from_ppstructure_label(d)
        return d

    def rebuild_html_from_ppstructure_label(self, label_info):
        from html import escape

        html_code = label_info["html"]["structure"]["tokens"].copy()
        to_insert = [i for i, tag in enumerate(html_code) if tag in ("<td>", ">")]
        for i, cell in zip(to_insert[::-1], label_info["html"]["cells"][::-1]):
            if cell["tokens"]:
                cell = [
                    escape(token) if len(token) == 1 else token
                    for token in cell["tokens"]
                ]
                cell = "".join(cell)
                html_code.insert(i + 1, cell)
        html_code = "".join(html_code)
        html_code = "<html><body><table>{}</table></body></html>".format(html_code)
        return html_code

    def clip_white(self, im, bboxes):
        w, h = im.size
        bbox = np.array([x[2] for x in bboxes])
        xmin = bbox[:, :, 0].min()
        ymin = bbox[:, :, 1].min()
        xmax = bbox[:, :, 0].max()
        ymax = bbox[:, :, 1].max()
        rotate_center = ((xmin + xmax) >> 1, (ymin + ymax) >> 1)
        xmin = max(0, xmin - random.randint(20, 50))
        ymin = max(0, ymin - random.randint(20, 50))
        xmax = min(w, xmax + random.randint(50, 80))
        ymax = min(h, ymax + random.randint(50, 80))
        # TODO 旋转时在这个的地方做的
        rotate_ = random.uniform(-1, 1)
        im = im.rotate(
            rotate_,
            center=rotate_center,
            expand=True,
            fillcolor=(255, 255, 255),
        )

        # TODO: 背景模糊
        if self.backgroud == "gaussian_noise":
            im = GenerateTable.add_gaussian_noise_background(im)

        # TODO: 在这里加一点模糊
        gaussian_filter = ImageFilter.GaussianBlur(radius=1.5)
        im = im.filter(gaussian_filter)
        im = im.crop([xmin, ymin, xmax, ymax])

        bbox[:, :, 0] -= xmin
        bbox[:, :, 1] -= ymin
        # FIXME 这个地方根据旋转调整的, 并没有严格的公式证明

        bbox[:, :, 0] += abs(int(rotate_ * 20))
        bbox[:, :, 1] += abs(int(rotate_ * 20))
        print(bbox[:, :, 0].min(), bbox[:, :, 1].min())
        for item, box in zip(bboxes, bbox):
            item[2] = box.tolist()
        return im, bboxes

    @staticmethod
    def get_rotate_adjust(x1, x2, y1, y2, rotate_center, rotate_):
        import math
        # 将检测框的中心点转换为旋转后的坐标系
        center_x = (x1 + x2) / 2 - rotate_center[0]
        center_y = (y1 + y2) / 2 - rotate_center[1]

        # 计算旋转后的中心点坐标
        cos = math.cos(math.radians(rotate_))
        sin = math.sin(math.radians(rotate_))
        new_center_x = center_x * cos - center_y * sin
        new_center_y = center_x * sin + center_y * cos

        # 将旋转后的中心点坐标转换回原始坐标系
        new_center_x += rotate_center[0]
        new_center_y += rotate_center[1]

        # 计算旋转后的检测框的左上角和右下角坐标
        new_x1 = new_center_x - (x2 - x1) / 2
        new_y1 = new_center_y - (y2 - y1) / 2
        new_x2 = new_center_x + (x2 - x1) / 2
        new_y2 = new_center_y + (y2 - y1) / 2
        return 

    def html_to_img(self, html_content, id_count):
        """converts html to image"""
        self.driver.get("data:text/html;charset=utf-8," + html_content)
        self.driver.maximize_window()
        self.driver.set_window_size(
            width=self.brower_width, height=self.brower_height, windowHandle="current"
        )
        window_size = self.driver.get_window_size()
        max_height, max_width = window_size["height"], window_size["width"]
        # element = WebDriverWait(self.driver, 3).until(EC.presence_of_element_located((By.ID, '0')))
        contens = []
        for id in range(id_count):
            # e = driver.find_element_by_id(str(id))
            e = WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located((By.ID, str(id)))
            )
            txt = e.text.strip()
            lentext = len(txt)
            loc = e.location
            size_ = e.size
            xmin = loc["x"]
            ymin = loc["y"]
            xmax = int(size_["width"] + xmin)
            ymax = int(size_["height"] + ymin)

            contens.append(
                [lentext, txt, [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]]
            )

        screenshot = self.driver.get_screenshot_as_png()
        screenshot = Image.open(BytesIO(screenshot))
        # TODO:对图片进行倾斜处理

        im = screenshot.crop((0, 0, max_width, max_height))
        return im, contens

    def close(self):
        self.driver.stop_client()
        self.driver.quit()

    @staticmethod
    def gaussian_noise(height: int, width: int) -> Image:
        """
        Create a background with Gaussian noise (to mimic paper)
        使用高斯噪声创建背景（以模拟纸张）
        """

        # We create an all white image
        image = np.ones((height, width)) * 255

        # We add gaussian noise
        cv2.randn(image, 235, 10)

        return Image.fromarray(image).convert("RGBA")

    @staticmethod
    def add_gaussian_noise_background(screenshot):
        # 3. 使用浏览器的截图功能将整个页面截取下来，然后使用Pillow库中的Image.open函数打开截图，并将截图裁剪为整个页面窗口的大小。TODO: 图片的自然场景化
        h, w = screenshot.size
        background = GenerateTable.gaussian_noise(w, h)

        # 将图片进行二值化
        screenshot = ImageOps.grayscale(screenshot)
        threshold = 128
        screenshot = screenshot.convert("L").point(
            lambda x: 0 if x < threshold else 255, "1"
        )
        screenshot = screenshot.convert("RGB")
        # 将白色转成透明, 只留下黑色部分
        arr = np.array(screenshot)
        alpha = np.ones(arr.shape[:2], dtype=arr.dtype) * 255
        for i in range(arr.shape[0]):
            for j in range(arr.shape[1]):
                if all(arr[i, j] == [255, 255, 255]):
                    alpha[i, j] = 0
        screenshot.putalpha(Image.fromarray(alpha))

        # 在背景图像上使用alpha通道粘贴黑色部分
        background.paste(screenshot, (0, 0), screenshot)

        return background.convert("RGB")
