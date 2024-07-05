from db_manager import Case, session
from sqlalchemy import distinct

def show_all_data():
    """현재 DB의 모든 데이터를 출력합니다"""
    try:
        specific_cases = session.query(Case).filter(Case.id == id).all()
        return specific_cases
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
def search_by_justice_id(id):
    try:
        specific_cases = session.query(Case).filter(Case.id == id).all()
        return specific_cases
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
    
def search_by_class_name(name):
    try:
        specific_cases = session.query(Case).filter(Case.class_name == name).all()
        return specific_cases
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
def search_by_key_tag(key_tag):
    try:
        specific_cases = session.query(Case).filter(Case.keyword_tagg == key_tag).all()
        for case in specific_cases:
            print(case.keyword_tagg)
        return specific_cases
    except Exception as e:
        print(f"Error: {str(e)}")
        return None
    
def count_by_tag(key_tag):
    return session.query(Case).filter(Case.keyword_tagg == key_tag).count()

def count_class_name():
    return len(session.query(distinct(Case.class_name)).all())

def count_keyword_tag():
    return len(session.query(distinct(Case.keyword_tagg)).all())
