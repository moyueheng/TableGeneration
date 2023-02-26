"""
Description: 转成百度网盘AI大赛所需要的数据格式
"""
# 目录
from os.path import join as pjoin
import os
import cv2

work_space = pjoin(os.path.dirname(__file__), "output/simple_table")
img_dir = pjoin(work_space, "img")
gt_path = pjoin(work_space, "gt.txt")


# 把这些cell坐标绘制上去, 查看位置


def get_label(gt):
    filename = gt["filename"].split("/")[-1]

    x_set = set()
    y_set = set()
    spanning_cell_bbox = list()

    for cell in gt["html"]["cells"]:
        # bbox recorde for 4 point
        x_min, y_min = cell["bbox"][0][0]
        x_max, y_max = cell["bbox"][0][2]
        x_set.add(x_min)
        x_set.add(x_max)
        y_set.add(y_min)
        y_set.add(y_max)
        if "".join(cell["tokens"]).startswith("spanning_cell"):
            spanning_cell_bbox.append([[x_min, y_min], [x_max, y_max]])

    # 便利一次, 把和前一个差别小于5的删除
    def average_nearby(nums):
        i = 0
        while i < len(nums) - 1:
            j = i + 1
            while j < len(nums) and nums[j] - nums[i] < 5:
                j += 1
            if j - i > 1:
                avg = int(sum(nums[i:j]) / (j - i))
                nums[i:j] = [avg] * (j - i)
            i = j
        return sorted(list(set(nums)))

    x_li = average_nearby(sorted(list(x_set)))
    y_li = average_nearby(sorted(list(y_set)))
    row_bbox = []
    for i in range(len(y_li) - 1):
        box = []
        box.append((x_li[0], y_li[i]))  # 左上角坐标
        box.append((x_li[-1], y_li[i + 1]))  # 右下角坐标
        row_bbox.append(box)

    col_bbox = []
    for i in range(len(x_li) - 1):
        box = []
        box.append((x_li[i], y_li[0]))  # 左上角坐标
        box.append((x_li[i + 1], y_li[-1]))  # 右下角坐标
        col_bbox.append(box)

    # 表格标签
    table_bbox = [[(x_li[0], y_li[0]), (x_li[-1], y_li[-1])]]
    return filename, row_bbox, col_bbox, table_bbox, spanning_cell_bbox


if __name__ == "__main__":
    # 读取gt文件

    gt_li = list()
    with open(gt_path, "r") as f:
        for line in f.readlines():
            gt_li.append(eval(line))
    gen_annos = {}
    from tqdm import tqdm

    for gt in tqdm(gt_li):
        # 将自带的gt标签转成百度网盘AI大赛需要的标签
        filename, row_bbox, col_bbox, table_bbox, spanning_cell_bbox = get_label(gt)
        gen_annos[filename] = list()
        for box in row_bbox:
            gen_annos[filename].append({"box": box[0] + box[1], "label": "row"})
        for box in col_bbox:
            gen_annos[filename].append({"box": box[0] + box[1], "label": "column"})
        for box in table_bbox:
            gen_annos[filename].append({"box": box[0] + box[1], "label": "table"})
        for box in spanning_cell_bbox:
            gen_annos[filename].append(
                {"box": box[0] + box[1], "label": "spanning_cell"}
            )
    import json

    with open(pjoin(work_space, "gen_annos.txt"), "w") as f:
        json.dump(gen_annos, f)
