# TraderJ Documentation Index

BTC/KRW 자동매매 봇 — 문서 목록

---

## plan/

기획, 로드맵, 피처 플랜

| 문서 | 설명 |
|------|------|
| [PROJECT_PLAN.md](plan/PROJECT_PLAN.md) | 프로젝트 종합 계획서 (5-Round 에이전트 팀 산출물 기반) |
| [전략개선.md](plan/전략개선.md) | AI Tuner 기획 — 레짐/전략 파라미터를 AI가 자동 최적화하는 모드 검토 |
| [dashboard-help-feature-plan.md](plan/dashboard-help-feature-plan.md) | 대시보드 도움말 기능 기획 (75개 용어집, ? 버튼 패널) |
| [profit-improvement-process.md](plan/profit-improvement-process.md) | 수익률 개선 프로세스 초안 — 백테스트→분석→최적화→적용→검증 사이클 |
| [profit-improvement-meeting_20260325.md](plan/profit-improvement-meeting_20260325.md) | 수익률 개선 프로세스 회의록 — Q1~Q6 결론 (bot-developer + system-architect) |

## design/

아키텍처, API, 전략 설계

| 문서 | 설명 |
|------|------|
| [round4-architecture-design.md](design/round4-architecture-design.md) | 엔진 아키텍처 설계 (Protocol 기반, 이벤트 드리븐, DI 컨테이너) |
| [round4-strategy-design.md](design/round4-strategy-design.md) | 전략 시스템 설계 (시그널 파이프라인, 프리셋, 레짐 전환) |
| [round4-dashboard-design.md](design/round4-dashboard-design.md) | 대시보드 UI/UX 설계 (Next.js, 실시간 모니터링) |
| [api-design.md](design/api-design.md) | FastAPI 엔드포인트 스펙 (27개 API) |
| [round3-tech-decisions.md](design/round3-tech-decisions.md) | 기술 결정 기록 — DB, 프레임워크, 배포 등 주요 의사결정 |
| [regime-strategy-process.md](design/regime-strategy-process.md) | 레짐 감지 → 전략 전환 → 포지션 관리 프로세스 흐름 |
| [features/ai-tuner.design.md](design/features/ai-tuner.design.md) | AI Tuner 모듈 상세설계 (`engine/tuner/` 패키지) |
| [features/dashboard-backtest.design.md](design/features/dashboard-backtest.design.md) | 대시보드 백테스트 기능 상세설계 (UI + API 연동) |

## manual/

사용법, 가이드, 용어집

| 문서 | 설명 |
|------|------|
| [ENGINE_GUIDE.md](manual/ENGINE_GUIDE.md) | 엔진 종합 가이드 (설정, 실행, 컴포넌트 상세) |
| [api-guide.md](manual/api-guide.md) | API 사용 가이드 (엔드포인트별 요청/응답 예시) |
| [ai-strategy-tuning-guide.md](manual/ai-strategy-tuning-guide.md) | AI 전략 튜닝 가이드 (비개발자용 설명) |
| [signal-glossary.md](manual/signal-glossary.md) | 시그널 용어집 (8단계 파이프라인 각 지표 설명) |
| [deployment-runbook.md](manual/deployment-runbook.md) | Fly.io 배포 런북 (빌드, 시크릿, 볼륨, 롤백) |
| [regime-switch-guide.md](manual/regime-switch-guide.md) | 레짐 전환 가이드 (6-type 레짐, 전략 매핑) |

## archive/

완료된 분석, 리포트, 과거 문서 (31개)

[archive/](archive/) 폴더 참조
