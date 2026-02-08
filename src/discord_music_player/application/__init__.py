"""
Application Layer

Contains use cases, command/query handlers, and application services.
This layer orchestrates domain objects and infrastructure to fulfill use cases.

Structure:
- commands/: CQRS write operations (PlayTrackCommand, SkipTrackCommand, etc.)
- queries/: CQRS read operations (GetQueueQuery, GetCurrentTrackQuery, etc.)
- services/: Application services for complex orchestration
- dto/: Data Transfer Objects for API boundaries
- interfaces/: Port interfaces for infrastructure adapters
"""
