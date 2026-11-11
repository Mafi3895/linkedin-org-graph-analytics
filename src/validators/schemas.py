from enum import Enum
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    FETCHED = "fetched"
    NOT_AVAILABLE = "not_available"
    ACCESS_RESTRICTED = "access_restricted"
    NOT_ATTEMPTED = "not_attempted"


class FieldAvailability(BaseModel):
    status: FieldStatus
    reason: Optional[str] = None
    source_element: Optional[str] = None


class BasicInformation(BaseModel):
    full_name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    about: Optional[str] = None
    current_company: Optional[str] = None


class WorkExperienceItem(BaseModel):
    company: Optional[str] = None
    job_title: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: Optional[bool] = None
    source_url: Optional[str] = None
    availability_status: FieldStatus = FieldStatus.FETCHED
    notes: Optional[str] = None


class EducationItem(BaseModel):
    institution: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    source_url: Optional[str] = None
    availability_status: FieldStatus = FieldStatus.FETCHED


class SkillItem(BaseModel):
    skill_name: str


class InterestItem(BaseModel):
    name: str
    category: Optional[str] = None
    source_url: Optional[str] = None


class ActivityEngagement(BaseModel):
    reactions: Optional[int] = None
    comments: Optional[int] = None


class ActivityItem(BaseModel):
    activity_id: Optional[str] = None
    activity_type: str  # post, repost, reaction, comment
    author: Optional[str] = None
    content: Optional[str] = None
    relative_time: Optional[str] = None
    exact_timestamp_utc: Optional[str] = None
    post_url: Optional[str] = None
    engagement: Optional[ActivityEngagement] = None


class LinkedInProfileRecord(BaseModel):
    person_id: str
    profile_url: str
    source_platform: str = "linkedin"
    fetched_at: str
    collection_method: str
    verification_status: str
    field_level_availability: Dict[str, FieldAvailability]
    basic_info: BasicInformation
    work_experience: List[WorkExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    skills: List[SkillItem] = Field(default_factory=list)
    interests: List[InterestItem] = Field(default_factory=list)
    activity: List[ActivityItem] = Field(default_factory=list)
    limitations_summary: str
