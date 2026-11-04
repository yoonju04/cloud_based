# 인프라 스케치 — 배포하지 않음

`infra/terraform/`은 수업 제안서의 AWS 매핑을 HCL로 옮긴 것입니다. **적용하지 않습니다.** 42dot 프로덕션 시스템이 아니고, 이 저장소를 클론했다고 계정이 생기지 않습니다. 자격 증명을 넣지 마세요.

`terraform validate`는 문법 검사용입니다. `terraform plan` / `apply`는 `allow_apply` 기본값 false와 `proposal_guard` precondition 때문에 거부됩니다. 그 변수를 true로 바꾸는 것은 이 과제의 범위가 아닙니다.

## 리소스

| 파일 | 리소스 | 제안서에서의 역할 |
| --- | --- | --- |
| `dynamodb.tf` | jobs, idempotency, packages | 조건부 상태, lease 만료 조회, 멱등 키, 패키지 해시 |
| `sqs.tf` | work queue + DLQ | 작업 전달. **최소 한 번 전달. 중복은 정상** |
| `s3.tf` | evidence bucket, versioning, public access block | 로그와 봉인된 패키지 |
| `statemachine.asl.json`, `sfn.tf` | Step Functions | Claim → Dispatch → Commit. Commit은 `commit_count = 0` 조건 |
| `compute.tf` | ECS desired count 0, Batch queue DISABLED | 워커 자리. 이미지는 게시되지 않은 `example.invalid` |
| `iam.tf` | control plane, worker, auditor, state machine | 역할 분리 초안 |
| `cloudwatch.tf` | log group, DLQ alarm | 지표 자리. 관측된 알람이 아니다 |
| `network.tf` | VPC와 서브넷 | ECS/Batch가 참조할 네트워크 초안. NAT와 VPC 엔드포인트는 없음 |

실행 가능한 상태 기계는 `src/fts/jobs/control.py`입니다. ASL은 그 모양을 클라우드 서비스로 적을 때의 초안이며, 파이썬 구현과 한 줄씩 같다고 검증하지 않았습니다.

## SQS와 멱등성

워커는 메시지를 지운 뒤에도 같은 메시지가 다시 보일 수 있습니다. 수신 측은 `idempotency_key`로 등록과 커밋을 구분해야 합니다. 같은 키는 같은 작업을 돌려주고 `commit_count`를 올리지 않습니다. 다른 키가 이미 확정된 job에 쓰기를 시도하면 조건부 쓰기가 실패합니다. DLQ는 그 이후의 실패를 담는 자리입니다. 이 스케치의 알람 임계값 0은 설계 메모이지, 발생한 장애가 아닙니다.

리전 기본값은 `ap-northeast-2`입니다. 미국 팀은 이 제안에서 두 번째 사일런트 리전을 갖는 것이 아니라, 같은 제어 평면을 호출합니다. 멀티 리전 복제는 설계하지 않았습니다.
