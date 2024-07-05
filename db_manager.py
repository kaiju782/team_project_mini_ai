import json
import os
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
Base = declarative_base()

#테이블을 구현하는 클래스입니다
#db_id, id, caseNm, caseTitle, courtType, courtNm, judmnAdjuDe, caseNo,jdgmn, jdgmnQuestion
#jdgmnAnswer, summary, summary_pass, keyword_tagg, reference_rules, reference_court_case
#class_name, instance_name

class Case(Base):
    __tablename__ = "cases"
    db_id = Column(Integer, primary_key=True, index=True)
    id = Column(Integer)
    caseNm = Column(String)
    caseTitle = Column(Text)
    courtType = Column(String)
    courtNm = Column(String) 
    judmnAdjuDe = Column(String)
    caseNo = Column(String)
    
    jdgmn = Column(Text)
    jdgmnQuestion = Column(Text)
    jdgmnAnswer = Column(Text)
    summary = Column(String)
    summary_pass = Column(String)
    keyword_tagg = Column(String)
    reference_rules = Column(Text)
    reference_court_case = Column(Text)
    class_name = Column(String)
    instance_name = Column(String)

class JudgmentInfo(Base):
    __tablename__ = 'judgment_info'

    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey('cases.id'))
    question = Column(Text)
    answer = Column(String)

# 데이터베이스 생성 설정
engine = create_engine(f'sqlite:///legal_cases.db')
SessionMaker = sessionmaker(bind=engine)
session = SessionMaker()

def load_data_from_db(db_name):
    Base.metadata.create_all(engine)
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT * FROM your_table_name"))
            data = result.fetchall()
        return data
    except SQLAlchemyError as e:
        return None
def process_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    try:
        #json에 있는 것 중에서 원하는 것만 뽑아내서 DB에 추가합니다
        #info, id
        case = Case(
            id=data['info']['id'],
            caseNm=data['info']['caseNm'],
            caseTitle=data['info']['caseTitle'],
            courtType=data['info']['courtType'],
            courtNm=data['info']['courtNm'],
            judmnAdjuDe=data['info']['judmnAdjuDe'],
            caseNo=data['info']['caseNo'],
            jdgmn=data['jdgmn'],
            jdgmnQuestion=data['jdgmnInfo'][0]['question'],
            jdgmnAnswer=data['jdgmnInfo'][0] ['answer'],
            summary= data['Summary'][0]['summ_contxt'],
            summary_pass = data['Summary'][0]['summ_pass'],
            keyword_tagg= data['keyword_tagg'][0]['keyword'],
            reference_rules=data['Reference_info']['reference_rules'],
            reference_court_case=data['Reference_info']['reference_court_case'],
            class_name=data['Class_info']['class_name'],
            instance_name=data['Class_info']['instance_name']
        )
        
        session.add(case)
        
        #jdgmnInfo는 다른 데이터로서
        for judgment_info in data['jdgmnInfo']:
            judgment = JudgmentInfo(
                case_id=case.id,
                question=judgment_info['question'],
                answer=judgment_info['answer']
            )
            session.add(judgment)
        
        session.commit()
        print(f"파일 {file_path}의 데이터가 성공적으로 저장되었습니다.")
    
    except Exception as e:
        session.rollback()
        print(f"파일 {file_path} 처리 중 오류 발생: {str(e)}")
    
        
def process_directory(directory_path):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                process_file(file_path)
def load(filepath):
    # 지정된 디렉토리의 모든 JSON 파일을 불러오기
    process_directory(filepath)

#데이터 불러오는 함수
#load('C:\\Users\\admin\\Downloads\\proj_mini\\TL')
session.close()