# _*_ coding:utf-8 _*_
# @File  : report.py
# @Time  : 2020-09-30 13:34
# @Author: zizle

""" 管理报告的API
API-1: 网络上传报告文件
API-2: 条件查询报告
API-3: 删除报告
API-4: 隐藏或公开报告
"""
import os
from fastapi import APIRouter, Depends, Form, UploadFile, HTTPException, Query, Body
from utils.verify import oauth2_scheme, decipher_user_token
from db.mysql_z import MySqlZ
from configs import FILE_STORAGE

report_router = APIRouter()


REPORT_TYPE_DICT = {
    "daily": "每日报告",
    "weekly": "周度报告",
    "monthly": "月度报告",
    "annual": "年度报告",
    "special": "专题报告",
    "others": "其他",
}


@report_router.post("/report-file/", summary="上传报告文件")
async def create_report(
        user_token: str = Depends(oauth2_scheme),
        report_file: UploadFile = Form(...),
        date: str = Form(...),
        relative_varieties: str = Form(...),
        report_type: str = Form(...),
        rename_text: str = Form('')
):
    # 从网络上传的文件信息保存报告
    user_id, _ = decipher_user_token(user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unknown User")
    # 验证report_type:
    if report_type not in ["daily", "weekly", "monthly", "annual", "special", "others"]:
        raise HTTPException(status_code=400, detail="Unknown Report Type")
    # 创建保存的文件夹
    date_folder = date[:7]  # 以月为单位保存
    variety_en = relative_varieties.split(';')[0]
    # 创建新文件所在路径
    save_folder = "REPORTS/{}/{}/{}/".format(variety_en, report_type, date_folder)
    report_folder = os.path.join(FILE_STORAGE, save_folder)
    if not os.path.exists(report_folder):
        os.makedirs(report_folder)
    filename = report_file.filename
    if rename_text:
        filename = rename_text + ".pdf"
    report_path = os.path.join(report_folder, filename)
    sql_path = os.path.join(save_folder, filename)
    # 创建数据库记录
    with MySqlZ() as cursor:
        cursor.execute(
            "SELECT id,filepath FROM research_report WHERE filepath=%s;", (sql_path, )
        )
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO research_report (`date`,creator,variety_en,report_type,filepath) "
                "VALUES (%s,%s,%s,%s,%s);",
                (date, user_id, relative_varieties, report_type, sql_path)
            )
        content = await report_file.read()      # 将文件保存到目标位置
        with open(report_path, "wb") as fp:
            fp.write(content)
        await report_file.close()
    return {"message": "上传成功!"}


@report_router.get("/report-file/", summary="条件查询报告信息")
async def get_report_info(
        query_date: str = Query(...),
        report_type: str = Query(...),
        variety_en: str = Query(...)
):
    # 验证report_type:
    if report_type not in ["daily", "weekly", "monthly", "annual", "special", "others"]:
        raise HTTPException(status_code=400, detail="Unknown Report Type")
    with MySqlZ() as cursor:
        cursor.execute(
            "SELECT id,`date`,variety_en,report_type,filepath,is_active FROM research_report "
            "WHERE `date`=%s AND report_type=%s AND LOCATE(%s,variety_en) > 0;",
            (query_date, report_type, variety_en)
        )
        reports = cursor.fetchall()
    # 处理文件名
    for report_item in reports:
        report_item["filename"] = os.path.split(report_item["filepath"])[1]
        report_item["type_text"] = REPORT_TYPE_DICT.get(report_item["report_type"], '')
    return {"message": "查询成功!", "reports": reports}


@report_router.put("/report-file/{report_id}/")
async def change_report_info(
        report_id: int,
        user_token: str = Depends(oauth2_scheme),
):
    user_id, _ = decipher_user_token(user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unknown User")
    with MySqlZ() as cursor:
        cursor.execute(
            "UPDATE research_report SET is_active=IF(is_active=0,1,0) "
            "WHERE creator=%s AND id=%s;", (user_id, report_id)
        )
    return {"message": "修改成功!"}


@report_router.delete("/report-file/{report_id}/")
async def delete_report_file(
        report_id: int,
        user_token: str = Depends(oauth2_scheme),
):
    user_id, _ = decipher_user_token(user_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unknown User")

    with MySqlZ() as cursor:
        cursor.execute(
            "SELECT id,filepath,creator FROM research_report WHERE id=%s;", (report_id, )
        )
        report_info = cursor.fetchone()
        if not report_info:
            raise HTTPException(status_code=400, detail="Unknown Report")
        # 是否是创建者删除
        if report_info["creator"] != user_id:
            # 查询用户是否是管理员
            cursor.execute("SELECT id,role FROM user_user WHERE id=%s;", (user_id, ))
            user_info = cursor.fetchone()
            if not user_info:
                raise HTTPException(status_code=401, detail="Unknown User")
            if user_info["role"] not in ["superuser", "operator"]:
                return {"message": "不能删除别人上传的报告!"}
        # 删除报告
        cursor.execute(
            "DELETE FROM research_report WHERE id=%s;", (report_id, )
        )
        report_path = os.path.join(FILE_STORAGE, report_info["filepath"])
        if os.path.exists(report_path) and os.path.isfile(report_path):
            os.remove(report_path)
    return {"message": "删除成功!"}
