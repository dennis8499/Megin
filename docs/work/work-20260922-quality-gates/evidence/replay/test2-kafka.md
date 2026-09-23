# Test2: Kafka full-flow replay

- Context: `/root/replay_test2_kafka` (fresh, read-only)
- Source: `C:\Users\denni\OneDrive\Desktop\新增資料夾\Test2`
- Verdict: SCN-009 full flow unverified

## Raw reviewer result

SCN-009’s full flow is **unverified**. The recorded Kafka container test failed before startup because Docker was unavailable. Even if it passed, it would prove only raw Confluent publish, consume, and direct commit; it never runs the service’s inbox, Quartz scheduling, HTTP execution, or commit ordering.

Passing coverage uses in-memory stores, a recording scheduler, configuration checks, and an API test with the subscription disabled. It does not prove broker redelivery, retry, or end-to-end idempotency. A further code concern is that HTTP failure sets the inbox to `Failed`, while redelivery reopens `Failed` for scheduling, contrary to the [plan’s duplicate-consume rule](</C:/Users/denni/OneDrive/Desktop/新增資料夾/Test2/docs/work/work-20260922-quartz-service/plan.md:148>). See [coordinator](</C:/Users/denni/OneDrive/Desktop/新增資料夾/Test2/src/QuartzSchedulerService/Kafka/KafkaEventCoordinator.cs:48>), [SQL transition](</C:/Users/denni/OneDrive/Desktop/新增資料夾/Test2/src/QuartzSchedulerService/Persistence/Kafka/SqlKafkaStores.cs:275>), and [HTTP failure state](</C:/Users/denni/OneDrive/Desktop/新增資料夾/Test2/src/QuartzSchedulerService/Jobs/HttpEndpointJob.cs:90>).

## Evidence locations from reviewer notes

- Contract: `features/quartz-service.feature:64-69`.
- Container test: `KafkaContainerTests.cs:13-69`; direct `consumer.Commit(result)` at line 62.
- Docker failure: `evidence/verification.md:24-26,46-48`.
- Local test substitutes: `KafkaBridgeTests.cs:11-35,55-75,105-136`; `KafkaApiTests.cs:19-45`.
- Service path not covered as a unit: `KafkaConsumerWorker.cs:189-304`, `KafkaMessageDispatcher.cs:42-65`, `KafkaQuartzOneOffScheduler.cs:38-69`.
