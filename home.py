import streamlit as st
import openai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
from PIL import Image
from io import BytesIO

# 페이지 설정 - 아이콘과 제목 설정
st.set_page_config(
    page_title="스마트 학습지",  # 추천된 제목 사용
    page_icon="📚",  # 브라우저 탭에 표시될 아이콘 (이모지 또는 이미지 파일 경로)
)

# Streamlit의 기본 메뉴와 푸터 숨기기
hide_menu_style = """
    <style>
    #MainMenu {visibility: hidden; }
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
"""
st.markdown(hide_menu_style, unsafe_allow_html=True)

# OpenAI API 클라이언트 초기화
client = openai.OpenAI(api_key=st.secrets["api"]["keys"][0])

# Google Sheets 인증 설정
credentials_dict = json.loads(st.secrets["gcp"]["credentials"])
credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
])
gc = gspread.authorize(credentials)

# 스프레드시트 열기
spreadsheet = gc.open(st.secrets["google"]["spreadsheet_name"])
worksheet = spreadsheet.sheet1

# 페이지에 제목 표시
st.title("스마트 학습지")

# 메인 컨테이너
with st.container():
    st.markdown("<div class='main-container'>", unsafe_allow_html=True)

    # 학생 이름 입력
    student_name = st.text_input("👤 학생 이름 입력")

    # 활동 코드 입력
    activity_code = st.text_input("🔑 활동 코드 입력")

    def decode_base64_image(image_base64):
        """Base64로 인코딩된 이미지를 디코딩하여 PIL 이미지 객체로 변환."""
        image_data = base64.b64decode(image_base64.split(',')[1])
        image = Image.open(BytesIO(image_data))
        return image

    if st.button("📄 문제 불러오기", key="get_questions"):
        with st.spinner("🔍 문제를 불러오는 중..."):
            data = worksheet.get_all_records()
            st.session_state.questions = {}
            st.session_state.images = {}
            st.session_state.teacher_email = None
            
            for row in data:
                if str(row.get('Activity_Code')) == activity_code:
                    st.session_state.questions = {
                        "Question1": row.get('Question1'),
                        "Question2": row.get('Question2'),
                        "Question3": row.get('Question3')
                    }
                    st.session_state.images = {
                        "Image1_URL": row.get('Image1_URL'),
                        "Image2_URL": row.get('Image2_URL'),
                        "Image3_URL": row.get('Image3_URL')
                    }
                    st.session_state.teacher_email = row.get('Email')
                    st.session_state.prompt = "학생의 답변을 분석하고, 한글로 피드백을 제공해주세요."  # 기본 프롬프트를 초기화
                    break

    if "questions" in st.session_state and st.session_state.questions:
        st.success("✅ 문제를 성공적으로 불러왔습니다.")
        for i in range(1, 4):
            st.markdown(f"<div class='question-title'>Question {i}:</div>", unsafe_allow_html=True)
            st.write(st.session_state.questions[f"Question{i}"])
            image_url = st.session_state.images.get(f"Image{i}_URL")
            if image_url and image_url.startswith("data:image/jpeg;base64,"):
                image = decode_base64_image(image_url)
                st.image(image, caption=f"Question {i} 관련 이미지")

            st.session_state[f"answer{i}"] = st.text_area(f"📝 Question {i} 답변", value=st.session_state.get(f"answer{i}", ""))

        if st.button("🤖 인공지능 피드백 받기", key="get_ai_feedback"):
            with st.spinner("💬 AI가 답변을 검토 중..."):
                # 학생의 답변과 문제를 하나의 문자열로 합치는 부분
                student_input = "\n\n".join([
                    f"Question {i}: {st.session_state.questions[f'Question{i}']}\nAnswer: {st.session_state[f'answer{i}']}" 
                    for i in range(1, 4)
                ])
                
                # AI에게 전달되는 프롬프트
                response = client.chat.completions.create(
                    model="gpt-4o-mini",  # 모델명
                    messages=[
                        {"role": "system", "content": st.session_state.prompt},
                        {"role": "user", "content": student_input}
                    ]
                )
                st.session_state.ai_answer = response.choices[0].message.content.strip()
                st.write("💡 **AI 피드백:** " + st.session_state.ai_answer)

        if "ai_answer" in st.session_state:
            st.write("💬 AI 피드백이 완료되었습니다. 필요시 답변을 수정할 수 있습니다.")

        # 학생의 소감 및 수정 사항 입력
        student_comments = st.text_area("✍️ 소감 및 수정 사항 입력", placeholder="예: 2번 답을 5로 고치겠습니다. 왜냐하면...")

        st.markdown("<div class='submit-button'>", unsafe_allow_html=True)
        if st.button("📧 답변 제출하기", key="submit_answers"):
            final_responses = "\n\n".join([
                f"Question {i}: {st.session_state.questions[f'Question{i}']}\nAnswer: {st.session_state[f'answer{i}']}"
                for i in range(1, 4)
            ])
            
            # 이메일로 교사에게 전송
            teacher_email = st.session_state.teacher_email
            if teacher_email:
                try:
                    msg = MIMEMultipart()
                    msg['From'] = st.secrets["email"]["address"]
                    msg['To'] = teacher_email
                    msg['Subject'] = f"{student_name}학생의 수행평가 답변 제출 - {activity_code}"

                    body = (
                        f"학생 이름: {student_name}\n\n"
                        f"학생이 수행평가 답변을 제출했습니다.\n\n"
                        f"{final_responses}\n\n"
                        f"AI 피드백:\n{st.session_state.get('ai_answer', '')}\n\n"
                        f"학생의 소감 및 수정 사항:\n{student_comments}"
                    )
                    msg.attach(MIMEText(body, 'plain'))

                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login(st.secrets["email"]["address"], st.secrets["email"]["password"])
                    text = msg.as_string()
                    server.sendmail(st.secrets["email"]["address"], teacher_email, text)
                    server.quit()

                    st.success("✅ 답변이 성공적으로 제출되었습니다!")
                except Exception as e:
                    st.error(f"❌ 이메일 전송 중 오류가 발생했습니다: {str(e)}")
            else:
                st.error("❌ 교사의 이메일 주소가 제공되지 않았습니다.")
        st.markdown("</div>", unsafe_allow_html=True)  # submit-button div 종료
    else:
        st.info("활동 코드를 입력하여 문제를 불러오세요.")

    st.markdown("</div>", unsafe_allow_html=True)  # main-container div 종료
