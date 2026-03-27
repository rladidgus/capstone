import asyncio
from dotenv import load_dotenv

load_dotenv()

from app.services.llm_service import LLMService

async def test_my_llm():
    print("🤖 Ollama LLM 통신 테스트 시작...")
    service = LLMService()
    
    print(f"📡 연결 대상: {service.base_url}")
    print(f"🧠 모델 이름: {service.model}")
    print("\n프롬프트 전송 중: '안녕하세요. 당신은 소상공인을 위한 경영 비서입니다. 인사 한 마디 해주세요.'")
    
    try:
        response = await service.generate_text("안녕하세요. 당신은 소상공인을 위한 경영 비서입니다. 인사 한 마디 해주세요.")
        print("\n✅ 대성공! AI의 답변입니다:")
        print("--------------------------------------------------")
        print(response.strip())
        print("--------------------------------------------------")
    except Exception as e:
        print(f"\n❌ 통신 에러 발생: {e}")
        print("\n[체크사항]")
        print("1. 맥 화면 상단 메뉴바에 귀여운 라마(Ollama) 아이콘이 켜져 있나요?")
        print("2. .env 파일에 OLLAMA_MODEL 이름이 본인이 가진 모델 이름과 똑같이 적혀있나요?")

if __name__ == "__main__":
    asyncio.run(test_my_llm())
