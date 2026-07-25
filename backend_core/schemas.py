from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    appName: Optional[str] = None
    appEnvironment: Optional[str] = None
    serverTime: Optional[str] = None
    serverDate: Optional[str] = None
    sqliteDbPath: Optional[str] = None
    sqliteDbExists: Optional[bool] = None
    sqliteDbDirectory: Optional[str] = None
    sqliteDbDirectoryWritableHint: Optional[bool] = None
    publicSnapshotPath: Optional[str] = None
    publicSnapshotExists: Optional[bool] = None
    datasetPath: Optional[str] = None
    datasetExists: Optional[bool] = None
    drainagePath: Optional[str] = None
    drainageExists: Optional[bool] = None
    templatePath: Optional[str] = None
    templateExists: Optional[bool] = None
    adminOverrideFilePath: Optional[str] = None
    adminApiProtected: Optional[bool] = None
    corsOrigins: Optional[list[str]] = None


class AdminOverrideRequest(BaseModel):
    districtName: str = Field(..., min_length=1)
    drainageCondition: Optional[str] = ""


class GenericStatusResponse(BaseModel):
    status: str
    message: str


class AdminOverrideResponse(GenericStatusResponse):
    districtName: str
    districtLabel: str
    hasOverride: bool
    drainageCondition: Optional[str] = None


class PublishResponse(GenericStatusResponse):
    publishedAt: Optional[str] = None


class PublicationStateResponse(BaseModel):
    hasPublishedSnapshot: bool = False
    publishedAt: Optional[str] = None
    payloadUpdatedAt: Optional[str] = None
    publishedDistrictCount: int = 0
    sourceLabel: Optional[str] = None
    generatedFromLiveAt: Optional[str] = None


class JsonEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
