import os
import tempfile
import pdfplumber
from difflib import SequenceMatcher

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup


API_TOKEN = os.getenv(8222021065:AAG3jd0GJHQ2-ucz-vJrIBpS-PReSTEfA_4)  # من Render (Environment Variable)

if not API_TOKEN:
    raise ValueError("❌ BOT_TOKEN غير موجود. أضفه كمتغير بيئة في Render.")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_pdf = State()


def normalize_arabic(s: str) -> str:
    """توحيد النص العربي للبحث"""
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    return s.strip().lower()


def similar(a, b):
    """نسبة التشابه بين نصين"""
    return SequenceMatcher(None, normalize_arabic(a), normalize_arabic(b)).ratio()


def extract_table_grades(pdf_path):
    """يقرأ كل الجداول من PDF ويحولها لقاموس: {اسم الطالب: العلامة}"""
    data = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row:
                        continue
                    # افترض أن العمود الأخير = العلامة
                    name = " ".join(row[:-1]).strip()
                    grade = row[-1].strip() if row[-1] else None
                    if name and grade:
                        data[name] = grade
    return data


@dp.message_handler(commands=["start", "reset"])
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("👋 أهلًا! اكتب اسمك الكامل أولًا:")
    await Form.waiting_for_name.set()


@dp.message_handler(state=Form.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def get_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(student_name=name)
    await message.reply("✅ استلمت اسمك.\nالآن ابعت ملف PDF جدول العلامات.")
    await Form.waiting_for_pdf.set()


@dp.message_handler(state=Form.waiting_for_pdf, content_types=types.ContentTypes.DOCUMENT)
async def handle_pdf(message: types.Message, state: FSMContext):
    if message.document.mime_type != "application/pdf":
        await message.reply("❌ الملف لازم يكون PDF.")
        return

    data = await state.get_data()
    student_name = data.get("student_name", "")

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        await message.document.download(destination_file=tmp_path)

        # استخراج البيانات من الجدول
        grades = extract_table_grades(tmp_path)

        # البحث عن الاسم
        best_match = None
        best_score = 0
        for name, grade in grades.items():
            score = similar(student_name, name)
            if score > best_score:
                best_match = (name, grade)
                best_score = score

        if best_match and best_score > 0.75:  # شرط التشابه 75%
            await message.reply(f"📄 الاسم: {best_match[0]}\n🎯 العلامة: {best_match[1]}")
        else:
            await message.reply("❌ لم أتمكن من العثور على اسمك في الجدول.")

    except Exception as e:
        await message.reply(f"⚠️ صار خطأ أثناء قراءة الملف: {e}")
    finally:
        os.remove(tmp_path)
        await state.finish()


@dp.message_handler(state=Form.waiting_for_pdf)
async def reject_non_pdf(message: types.Message):
    await message.reply("❌ أرسل ملف PDF فقط.")
    

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
