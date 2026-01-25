"""
SmartHire Backend API
=====================

A production-ready FastAPI service for AI-powered resume analysis and candidate
evaluation. Implements a 3-tier AI analysis system with intelligent failover.

Architecture:
    Tier 1: Groq (Llama 3.1 70B) - Ultra-fast LPU inference, primary analysis
    Tier 2: Google Gemini 2.0 Flash - Backup AI with quality fallback
    Tier 3: Keyword Analysis - Always-available fallback for reliability

Features:
    - Multi-tier AI analysis with automatic provider failover
    - PDF resume parsing and intelligent text extraction
    - Multi-model support (Groq, Gemini, Keyword-based)
    - Generous scoring algorithm (focuses on candidate potential)
    - Structured JSON responses for easy frontend integration
    - Production-ready error handling and logging
    - CORS configuration for security (environment-aware)
    - Health check endpoint for deployment monitoring

API Endpoints:
    GET  /health                    - Service health check
    POST /analyze-resume            - Full AI analysis with all tiers
    POST /analyze-resume/basic      - Text extraction only (no AI)

Environment Configuration:
    GROQ_API_KEY        - Required for Tier 1 AI analysis
    GEMINI_API_KEY      - Optional for Tier 2 backup AI
    ENVIRONMENT         - 'development' or 'production' (default: development)
    PORT                - Server port (default: 8000)

Requirements:
    - python >= 3.9
    - fastapi >= 0.104.0
    - uvicorn >= 0.24.0
    - groq >= 0.4.0
    - google-generativeai >= 0.3.0
    - PyMuPDF >= 1.23.0
    - pydantic >= 2.0.0
    - python-dotenv >= 1.0.0

Author: Abdullah Ghaffar
Repository: https://github.com/abdullahghaffar/SmartHire
License: MIT
Version: 1.0.0
Created: January 2026
"""

import os
import sys
from pathlib import Path

# Configure working directory and Python path for proper imports
BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
sys.path.append(str(BASE_DIR))

# Standard library imports
import io
import json
import logging
import re
from typing import Optional

# Third-party imports
from dotenv import load_dotenv
import fitz  # PyMuPDF for PDF processing
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables from .env file for secure configuration
load_dotenv()

# Configure structured logging for production monitoring and debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize FastAPI application with metadata
app = FastAPI(
    title="SmartHire API",
    description="AI-powered resume analysis and candidate evaluation service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ============================================================
# CORS CONFIGURATION - Environment-Aware Security Settings
# ============================================================
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    # Production: Restrict to verified frontend domains only for security
    allowed_origins = [
        "https://smarthire.vercel.app",
        "https://your-custom-domain.com",
    ]
    logger.info("CORS configured for PRODUCTION - Restricted origins")
else:
    # Development: Allow localhost variants for local testing
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    logger.info("CORS configured for DEVELOPMENT - Localhost only")

# Add CORS middleware with strict HTTP method and header restrictions
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ============================================================
# PYDANTIC RESPONSE MODELS - Type-Safe API Responses
# ============================================================

class ResumeAnalysisResponse(BaseModel):
    """Response model for basic resume text extraction endpoint."""
    filename: str
    text_length: int
    extracted_text: str


class AIAnalysisResult(BaseModel):
    """Structured AI analysis results from any AI provider."""
    match_score: int
    key_strengths: list
    missing_skills: list
    summary: str
    email_draft: str


class EnhancedResumeAnalysisResponse(BaseModel):
    """Complete response including both text extraction and AI analysis."""
    filename: str
    text_length: int
    extracted_text: str
    ai_analysis: AIAnalysisResult


# ============================================================
# TIER 2: GEMINI AI CLIENT - Backup Intelligent Analysis
# ============================================================
import google.generativeai as genai


class GeminiAIClient:
    """
    Google Gemini 2.0 Flash AI client for backup resume analysis.
    
    Used as secondary AI provider when Groq is unavailable.
    Implements the same analysis interface as GroqAIClient for easy fallback.
    
    Attributes:
        api_key: Google Gemini API authentication key
        client: Initialized Gemini client instance
    """

    def __init__(self):
        """Initialize Gemini client with API key from environment."""
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.client = None

        if self.api_key:
            try:
                # Configure Gemini with API key for authentication
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel('gemini-1.5-flash')
                logger.info("Gemini AI initialized successfully (Backup Tier - gemini-1.5-flash)")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                self.api_key = None
                self.client = None
        else:
            logger.warning("GEMINI_API_KEY not found in environment - Gemini analysis unavailable")

    def is_available(self) -> bool:
        """
        Check if Gemini client is properly configured and ready to use.
        
        Returns:
            bool: True if client is initialized and API key is set, False otherwise
        """
        return bool(self.client and self.api_key)

    def analyze_resume(self, resume_text: str, job_description: str) -> dict:
        """
        Analyze resume against job requirements using Gemini AI.
        
        Falls back to keyword analysis if Gemini API call fails,
        ensuring analysis always completes regardless of provider availability.
        
        Args:
            resume_text: Extracted text from candidate resume
            job_description: Full job description and requirements
            
        Returns:
            dict containing analysis results:
                - match_score: Integer 0-100
                - key_strengths: List of candidate skills
                - missing_skills: List of skill gaps
                - summary: Professional assessment
                - email_draft: Interview/rejection template
        """
        # Attempt Gemini analysis first
        if self.is_available():
            try:
                return self._analyze_with_gemini(resume_text, job_description)
            except Exception as e:
                logger.warning(
                    f"Gemini API error ({type(e).__name__}): {str(e)[:100]}. "
                    "Falling back to keyword analysis."
                )

        # Fallback to keyword-based analysis
        return self._analyze_with_fallback(resume_text, job_description)

    def _analyze_with_gemini(self, resume_text: str, job_description: str) -> dict:
        """
        Send resume and job description to Gemini 2.0 Flash for intelligent analysis.
        
        Uses a carefully crafted prompt optimized for recruiting use cases
        with emphasis on candidate potential and transferable skills.
        
        Args:
            resume_text: Extracted resume text
            job_description: Job requirements text
            
        Returns:
            dict: Parsed analysis results from Gemini
            
        Raises:
            Exception: If API communication fails
        """
        # Limit resume length to avoid token limits (safety margin: 5000 chars)
        resume_clipped = resume_text[:5000] if len(resume_text) > 5000 else resume_text

        # Generous scoring prompt designed for recruiting context
        prompt = f"""You are a supportive Senior Technical Recruiter evaluating candidate potential.

CANDIDATE EVALUATION GUIDELINES:
- Be generous with scoring: 50%+ skill match should score 60 or higher
- Focus on transferable and adjacent skills
- Ignore PDF extraction artifacts, formatting issues, and typos
- Value soft skills like problem-solving, teamwork, communication
- Assume positive intent when information is unclear
- Minimum score is 30 only for completely irrelevant candidates

Job Requirements:
{job_description}

Candidate Resume:
{resume_clipped}

Provide analysis focusing on candidate potential and growth trajectory.

RESPONSE FORMAT: Return ONLY valid JSON (no markdown, no explanations):

{{
  "match_score": <integer 0-100, prioritize generosity>,
  "key_strengths": [<concrete skills from resume, max 5>],
  "missing_skills": [<areas for development, max 5>],
  "summary": "<2-3 sentences on potential and fit>",
  "email_draft": "<professional email - invite if score > 50, else polite decline>"
}}"""

        try:
            logger.info("Sending request to Gemini API for analysis...")

            # Call Gemini API with structured prompt
            response = self.client.generate_content(prompt)
            response_text = response.text

            logger.info(f"Gemini response received ({len(response_text)} characters)")

            # Clean and parse JSON response
            cleaned = clean_ai_response(response_text)
            parsed = self._parse_json_response(cleaned)

            # Enforce generous minimum score when candidate has demonstrated skills
            if parsed.get("match_score", 0) < 30 and len(parsed.get("key_strengths", [])) > 0:
                logger.info("Adjusting score upward per generous scoring policy")
                parsed["match_score"] = 35

            logger.info(f"Gemini analysis complete: match_score={parsed.get('match_score')}%")
            return parsed

        except Exception as e:
            logger.error(f"Gemini API error ({type(e).__name__}): {str(e)}")
            raise

    def _analyze_with_fallback(self, resume_text: str, job_description: str) -> dict:
        """
        Perform intelligent keyword-based analysis as Gemini fallback.
        
        Uses regex patterns to extract technical skills from job description,
        then matches them against resume. Generates personalized analysis
        based on skill gap analysis.
        
        Args:
            resume_text: Extracted resume text
            job_description: Job requirements text
            
        Returns:
            dict: Complete analysis results including score and email draft
        """
        logger.info("Using fallback keyword-based analysis")

        # Normalize text for consistent matching
        resume_lower = resume_text.lower()
        job_lower = job_description.lower()

        # Define comprehensive technical skill patterns
        skill_patterns = [
            r"\b(python|java|javascript|typescript|go|rust|c\+\+|ruby|php|swift|kotlin)\b",
            r"\b(react|angular|vue|node\.?js|express|django|flask|fastapi|spring|laravel)\b",
            r"\b(aws|azure|gcp|docker|kubernetes|k8s|terraform|ansible|jenkins|gitlab)\b",
            r"\b(postgresql|mysql|mongodb|redis|elasticsearch|cassandra|dynamodb)\b",
            r"\b(machine learning|deep learning|ai|nlp|computer vision|tensorflow|pytorch|scikit-learn)\b",
            r"\b(rest api|graphql|grpc|microservices|serverless|event-driven)\b",
            r"\b(git|github|gitlab|ci/cd|devops|agile|scrum|jira)\b",
            r"\b(html|css|sass|tailwind|bootstrap|material-ui|webpack|vite)\b"
        ]

        # Extract all skills mentioned in job description
        job_skills = set()
        for pattern in skill_patterns:
            matches = re.findall(pattern, job_lower)
            job_skills.update(matches)

        # Include capitalized technical terms (e.g., "AWS", "React")
        capitalized_words = re.findall(r"\b[A-Z][A-Za-z0-9+#\.]+\b", job_description)
        job_skills.update([w.lower() for w in capitalized_words if len(w) > 2])

        # Categorize skills as found or missing in resume
        found_skills = []
        missing_skills = []

        for skill in job_skills:
            if skill in resume_lower or skill.replace(".", "") in resume_lower:
                found_skills.append(skill)
            else:
                missing_skills.append(skill)

        # Calculate match percentage
        if len(job_skills) > 0:
            match_score = int((len(found_skills) / len(job_skills)) * 100)
        else:
            # Fallback to word overlap analysis
            resume_words = set(re.findall(r"\b\w+\b", resume_lower))
            job_words = set(re.findall(r"\b\w+\b", job_lower))
            common_words = resume_words.intersection(job_words)
            match_score = min(int((len(common_words) / len(job_words)) * 100), 100)

        # Ensure score is in valid range
        match_score = max(0, min(100, match_score))

        # Select key strengths and missing skills for display
        key_strengths = found_skills[:5] if found_skills else ["General background", "Relevant experience"]
        missing_skills_display = missing_skills[:5] if missing_skills else ["No critical gaps identified"]

        # Generate contextual summary based on match score
        if match_score >= 70:
            summary = (
                f"Strong candidate with {len(found_skills)} matching skills including "
                f"{', '.join(found_skills[:3])}. Demonstrates solid alignment with requirements."
            )
        elif match_score >= 50:
            summary = (
                f"Moderate fit with {len(found_skills)} relevant skills. "
                f"Experience in {', '.join(found_skills[:2]) if found_skills else 'related areas'} "
                f"would benefit from development in missing technical areas."
            )
        else:
            summary = (
                f"Limited alignment with {len(found_skills)} matching skills. "
                f"Significant skill development needed in {', '.join(missing_skills[:3]) if missing_skills else 'key technical areas'}."
            )

        # Generate professional email template
        if match_score >= 60:
            email_draft = f"""Hello,

Thank you for your interest in our position. Your background demonstrates promise 
with relevant experience in {', '.join(found_skills[:3]) if found_skills else 'applicable areas'}.

We would like to invite you for an initial interview to discuss your qualifications 
and how your experience aligns with our team's needs.

Please let us know your availability for a 30-minute call this week.

Best regards,
Hiring Team"""
        else:
            email_draft = """Hello,

Thank you for your application and interest in our position. After careful review 
of your qualifications, we have decided to move forward with other candidates 
whose experience more closely matches our immediate needs.

We encourage you to apply for future opportunities that align with your skillset, 
and we wish you success in your career.

Best regards,
Hiring Team"""

        logger.info(f"Fallback analysis complete: {len(found_skills)} skills matched, score={match_score}%")

        return {
            "match_score": match_score,
            "key_strengths": key_strengths,
            "missing_skills": missing_skills_display,
            "summary": summary,
            "email_draft": email_draft
        }

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """
        Extract and validate JSON from AI response text.
        
        Handles common AI output issues like missing fields and invalid types,
        applying sensible defaults when fields are missing.
        
        Args:
            text: Response text from AI (already cleaned of markdown)
            
        Returns:
            dict: Validated analysis with all required keys
            
        Raises:
            ValueError: If no valid JSON found in response
        """
        # Find JSON object in response text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)

        if not json_match:
            logger.error(f"No JSON object found in response: {text[:200]}")
            raise ValueError("AI response did not contain valid JSON")

        json_str = json_match.group(0)
        parsed = json.loads(json_str)

        # Validate required analysis fields exist
        required_keys = {"match_score", "missing_skills", "summary", "email_draft"}
        missing_keys = required_keys - set(parsed.keys())

        if missing_keys:
            logger.warning(f"AI response missing keys: {missing_keys}. Using defaults.")
            # Apply sensible defaults for missing fields
            for key in missing_keys:
                if key == "match_score":
                    parsed[key] = 0
                elif key == "missing_skills":
                    parsed[key] = []
                else:
                    parsed[key] = ""

        # Type validation and normalization
        if isinstance(parsed.get("match_score"), str):
            try:
                parsed["match_score"] = int(parsed["match_score"])
            except (ValueError, TypeError):
                parsed["match_score"] = 0

        # Ensure lists are actually lists
        if not isinstance(parsed.get("missing_skills"), list):
            parsed["missing_skills"] = [parsed.get("missing_skills", "")]

        return parsed


# ============================================================
# TIER 1: GROQ AI CLIENT - Primary Ultra-Fast Analysis
# ============================================================
from groq import Groq


class GroqAIClient:
    """
    Groq API client for primary resume analysis using Llama 3.1 70B.
    
    Groq provides ultra-fast LPU (Language Processing Unit) inference,
    typically completing analysis in under 2 seconds with high accuracy.
    This is the preferred primary AI tier for SmartHire.
    
    Features:
        - Ultra-fast inference on custom LPU hardware
        - Llama 3.1 70B model for high-quality analysis
        - Generous scoring algorithm for recruiting
        - Automatic fallback to Gemini if unavailable
    
    Attributes:
        api_key: Groq API authentication key
        client: Initialized Groq client instance
    """

    def __init__(self):
        """
        Initialize Groq client with API key from environment.
        
        Logs warnings if API key is missing rather than failing,
        allowing graceful fallback to backup AI providers.
        """
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = None

        if self.api_key:
            try:
                # Initialize Groq client for API communication
                self.client = Groq(api_key=self.api_key)
                logger.info("Groq AI initialized successfully (Llama 3.1 70B Primary Tier)")
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e}")
                self.api_key = None
        else:
            logger.warning("GROQ_API_KEY not found in environment - Groq analysis unavailable")

    def is_available(self) -> bool:
        """
        Check if Groq client is properly configured and ready to use.
        
        Returns:
            bool: True if client is initialized, False otherwise
        """
        return bool(self.client)

    def analyze_resume(self, resume_text: str, job_description: str) -> dict:
        """
        Analyze resume using Groq's Llama 3.1 70B model with ultra-fast LPU inference.
        
        Processes resume against job description, producing intelligent analysis
        with emphasis on candidate potential and transferable skills.
        
        Args:
            resume_text: Extracted text from candidate resume
            job_description: Full job description and requirements
            
        Returns:
            dict containing analysis results:
                - match_score: Integer 0-100 (generous scoring applied)
                - key_strengths: List of candidate strengths from resume
                - missing_skills: List of skill gaps
                - summary: Professional assessment summary
                - email_draft: Interview template or rejection letter
                
        Raises:
            ValueError: If API key not configured or API call fails
        """
        if not self.is_available():
            raise ValueError("Groq API key not configured - cannot perform analysis")

        # Limit resume to manage token usage (safety margin: 6000 chars)
        resume_clipped = resume_text[:6000] if len(resume_text) > 6000 else resume_text

        # Generous scoring prompt optimized for Llama 3.1 70B
        prompt = f"""You are an experienced Technical Recruiter evaluating candidate fit.

JOB REQUIREMENTS:
{job_description}

CANDIDATE RESUME:
{resume_clipped}

EVALUATION GUIDELINES:
- Be generous: candidates with 50%+ of required skills should score 60 or higher
- Value transferable skills (e.g., Python experience applies to backend roles)
- Emphasize potential, not just perfect matches
- Ignore PDF extraction artifacts and formatting issues
- Evaluate soft skills like problem-solving, teamwork, communication
- Minimum score is 30 only for completely irrelevant candidates

Analyze this candidate's fit for the role, focusing on strengths and potential.

REQUIRED RESPONSE FORMAT: Return ONLY valid JSON (no markdown, no code blocks):

{{
  "match_score": <integer 0-100, generous scoring>,
  "key_strengths": [<skills/experience from resume, max 5>],
  "missing_skills": [<areas for development, max 5>],
  "summary": "<2-3 sentences on potential and alignment>",
  "email_draft": "<professional email - invite if score > 50, else polite decline>"
}}"""

        try:
            logger.info("Sending analysis request to Groq API (Llama 3.1 70B - Ultra-Fast LPU)")

            # Call Groq API with structured prompt
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful recruiter AI that returns only valid JSON responses."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,  # Balanced creativity and consistency
                max_tokens=1000,  # Sufficient for detailed analysis
                top_p=1,
                stream=False
            )

            # Extract response text
            result_text = response.choices[0].message.content

            logger.info("Groq AI analysis completed (Ultra-Fast LPU Processing)")

            # Parse and validate JSON response
            analysis_result = self._parse_json_response(result_text)

            # Enforce generous minimum score when candidate has demonstrated skills
            if analysis_result.get("match_score", 0) < 35 and len(analysis_result.get("key_strengths", [])) > 0:
                analysis_result["match_score"] = 35

            logger.info(f"Groq analysis complete: match_score={analysis_result.get('match_score')}%")
            return analysis_result

        except Exception as e:
            logger.error(f"Groq API error ({type(e).__name__}): {str(e)[:100]}")
            raise ValueError(f"Groq AI analysis failed: {str(e)}")

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """
        Extract and validate JSON from Groq API response.
        
        Handles common issues with AI-generated responses and applies
        sensible defaults for missing fields to ensure reliable parsing.
        
        Args:
            text: Raw response text from Groq API
            
        Returns:
            dict: Validated analysis with all required keys and correct types
            
        Raises:
            ValueError: If no valid JSON found in response
        """
        # Clean markdown wrappers from response
        cleaned = clean_ai_response(text)

        # Extract JSON object from response
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        if not json_match:
            logger.error(f"No JSON found in Groq response: {cleaned[:200]}")
            raise ValueError("Groq response did not contain valid JSON")

        # Parse JSON string
        parsed = json.loads(json_match.group(0))

        # Validate required analysis fields exist
        required = {"match_score", "key_strengths", "missing_skills", "summary", "email_draft"}
        missing = required - set(parsed.keys())

        if missing:
            logger.warning(f"Groq response missing keys: {missing}. Applying defaults.")
            # Apply sensible defaults for missing fields
            for key in missing:
                if key == "match_score":
                    parsed[key] = 50
                elif key in ["key_strengths", "missing_skills"]:
                    parsed[key] = []
                else:
                    parsed[key] = ""

        # Type validation for match_score
        try:
            parsed["match_score"] = max(0, min(100, int(parsed.get("match_score", 50))))
        except (ValueError, TypeError):
            parsed["match_score"] = 50

        # Type validation for list fields
        for key in ["key_strengths", "missing_skills"]:
            if not isinstance(parsed.get(key), list):
                parsed[key] = [str(parsed[key])] if parsed.get(key) else []

        return parsed


# ============================================================
# AI CLIENT INITIALIZATION - 3-Tier Priority System
# ============================================================

# Tier 1: Groq (Primary - Ultra-fast, most reliable free tier)
groq_client = GroqAIClient()

# Tier 2: Gemini (Backup - High-quality fallback)
gemini_client = GeminiAIClient()

# Tier 3: Fallback keyword analysis (Always available, no API required)


# ============================================================
# UTILITY FUNCTIONS - Text Processing and Cleaning
# ============================================================


def clean_ai_response(text: str) -> str:
    """
    Clean AI response by removing markdown code block wrappers.
    
    Many LLMs wrap JSON responses in markdown syntax (```json ... ```).
    This utility strips those markers to prepare text for JSON parsing.
    
    Args:
        text: Raw response text from AI model
        
    Returns:
        Cleaned text with markdown removed and whitespace normalized
        
    Example:
        >>> text = '```json\\n{"key": "value"}\\n```'
        >>> clean_ai_response(text)
        '{"key": "value"}'
    """
    # Remove markdown code block markers (```json ... ```)
    text = re.sub(r"```(?:json)?\s*", "", text)

    # Remove any trailing code block markers
    text = text.replace("```", "")

    # Normalize whitespace
    text = text.strip()

    return text


def extract_text_from_pdf(file_stream: io.BytesIO, filename: str) -> str:
    """
    Extract text content from uploaded PDF file using PyMuPDF (fitz).
    
    Handles multi-page PDFs and common extraction issues while preserving
    document structure. Applies cleaning to improve downstream text analysis.
    
    Args:
        file_stream: BytesIO stream containing PDF binary data
        filename: Original filename for logging and error reporting
        
    Returns:
        Cleaned, concatenated text from all PDF pages
        
    Raises:
        ValueError: If PDF is corrupt, empty, or text extraction fails
    """
    try:
        # Open PDF from in-memory stream
        pdf_document = fitz.open(stream=file_stream, filetype="pdf")

        if pdf_document.page_count == 0:
            raise ValueError("PDF file contains no pages")

        # Extract text from all pages
        extracted_text = []
        for page_num in range(pdf_document.page_count):
            try:
                page = pdf_document[page_num]
                text = page.get_text()
                if text.strip():  # Only include pages with content
                    extracted_text.append(text)
            except Exception as e:
                logger.warning(
                    f"Error extracting page {page_num + 1} from {filename}: {str(e)}"
                )
                # Continue processing remaining pages

        pdf_document.close()

        if not extracted_text:
            raise ValueError("No extractable text found in PDF")

        # Combine pages and clean resulting text
        full_text = "\n".join(extracted_text)
        cleaned_text = clean_text(full_text)

        logger.info(f"Successfully extracted {len(cleaned_text)} characters from {filename}")
        return cleaned_text

    except fitz.FileError as e:
        logger.error(f"PDF file error for {filename}: {str(e)}")
        raise ValueError(f"Invalid or corrupt PDF file: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error processing {filename}: {str(e)}")
        raise ValueError(f"Error processing PDF: {str(e)}")


def clean_text(text: str) -> str:
    """
    Clean and normalize extracted PDF text for improved processing.
    
    Handles common PDF extraction issues while preserving document structure
    and semantic meaning. Applies multiple cleaning passes for reliability.
    
    Args:
        text: Raw text extracted from PDF
        
    Returns:
        Cleaned, normalized text ready for AI analysis
    """
    # Normalize whitespace (preserve single spaces within content)
    text = re.sub(r"[ \t]+", " ", text)

    # Fix hyphenated words split across lines (common PDF extraction issue)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

    # Normalize bullet points to consistent format
    text = re.sub(r"[•●○■□▪▫]", "-", text)
    text = re.sub(r"\*\s+", "- ", text)

    # Remove excessive punctuation
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"-{2,}", "-", text)

    # Remove page numbers (common PDF footer patterns)
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r"\n\s*Page\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n\s*\(Page\s+\d+\)\s*\n", "\n", text, flags=re.IGNORECASE)

    # Remove header/footer patterns
    text = re.sub(r"\n\s*[A-Za-z\s]+\d{1,2}\s*\n", "\n", text)

    # Normalize multiple line breaks (preserve paragraph structure)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Remove line breaks within sentences
    text = re.sub(r"([a-z])\n([a-z])", r"\1 \2", text)

    # Clean individual lines
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line:  # Keep non-empty lines only
            cleaned_lines.append(line)

    # Rejoin with normalized line breaks
    text = "\n".join(cleaned_lines)

    return text.strip()


# ============================================================
# API ENDPOINTS - Resume Analysis and Health Monitoring
# ============================================================


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring and load balancer health tests.
    
    Used for deployment monitoring and service availability verification.
    Returns immediately with minimal overhead, including AI provider status.
    
    Returns:
        dict: Service status, identification, and AI provider availability
    """
    return {
        "status": "healthy",
        "service": "SmartHire Backend",
        "ai_providers": {
            "groq": groq_client.is_available(),
            "gemini": gemini_client.is_available()
        }
    }


@app.post("/analyze-resume", response_model=EnhancedResumeAnalysisResponse)
async def analyze_resume(
    file: UploadFile = File(..., description="PDF resume file to analyze"),
    job_description: str = Form(..., description="Job requirements and description")
) -> EnhancedResumeAnalysisResponse:
    """
    Analyze resume against job description with full AI analysis pipeline.
    
    Complete endpoint for resume evaluation. Implements 3-tier AI fallback system:
    1. Groq (Ultra-fast LPU inference) - Primary tier
    2. Gemini 2.0 Flash (High-quality fallback) - Secondary tier
    3. Keyword analysis (Always available) - Tertiary tier

    Process Flow:
    1. Validate uploaded PDF file
    2. Extract text from PDF using PyMuPDF
    3. Run AI analysis through 3-tier system
    4. Generate structured JSON response

    Args:
        file: PDF resume file (multipart/form-data)
        job_description: Full job description and requirements text
        
    Returns:
        EnhancedResumeAnalysisResponse containing:
            - filename: Original uploaded file name
            - text_length: Length of extracted resume text
            - extracted_text: Full resume text from PDF
            - ai_analysis: Structured analysis results
            
    Raises:
        HTTPException 400: Invalid file format or empty description
        HTTPException 500: Unexpected processing error
    """
    # Validate file is proper PDF
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        logger.warning(f"Invalid file type: {file.content_type} for {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF document. Uploaded file is not a valid PDF."
        )

    if not file.filename.lower().endswith(".pdf"):
        logger.warning(f"Invalid file extension: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File name must end with .pdf extension"
        )

    try:
        # Validate job description content
        if not job_description or not job_description.strip():
            raise HTTPException(
                status_code=400,
                detail="Job description cannot be empty or whitespace-only"
            )

        # Read uploaded file into memory stream
        file_content = await file.read()

        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty or cannot be read"
            )

        file_stream = io.BytesIO(file_content)

        # Step 1: Extract text from PDF
        extracted_text = extract_text_from_pdf(file_stream, file.filename)

        logger.info(f"Extracted {len(extracted_text)} characters from {file.filename}")

        # Step 2: Run 3-tier AI analysis with automatic failover
        logger.info(f"Starting 3-tier AI analysis for {file.filename}")

        ai_result = None
        ai_source = None

        # Tier 1: Groq (Ultra-fast primary tier)
        if groq_client.is_available():
            try:
                logger.info("Tier 1: Attempting Groq (Llama 3.1 70B - Ultra-Fast LPU)")
                ai_result = groq_client.analyze_resume(extracted_text, job_description)
                ai_source = "Groq (Primary - Llama 3.1 70B)"
                logger.info(f"Success: {ai_source}")
            except Exception as e:
                logger.warning(f"Groq failed ({type(e).__name__}): {str(e)[:100]}")
                ai_result = None
        else:
            logger.warning("Groq not available - proceeding to Tier 2")

        # Tier 2: Gemini (High-quality backup tier)
        if ai_result is None and gemini_client.is_available():
            try:
                logger.info("Tier 2: Attempting Gemini 2.0 Flash (Backup AI)")
                ai_result = gemini_client.analyze_resume(extracted_text, job_description)
                ai_source = "Gemini 2.0 Flash (Backup)"
                logger.info(f"Success: {ai_source}")
            except Exception as e:
                logger.warning(f"Gemini failed ({type(e).__name__}): {str(e)[:100]}")
                ai_result = None

        # Tier 3: Keyword analysis (Always-available fallback)
        if ai_result is None:
            try:
                logger.info("Tier 3: Using Keyword Analysis (Always-Available Fallback)")
                fallback_client = GeminiAIClient()
                ai_result = fallback_client._analyze_with_fallback(extracted_text, job_description)
                ai_source = "Keyword Analysis (Tier 3 Fallback)"
                logger.info(f"Success: {ai_source}")
            except Exception as e:
                logger.error(f"All tiers failed: {str(e)}")
                # Return safe default response
                ai_result = {
                    "match_score": 0,
                    "key_strengths": [],
                    "missing_skills": [],
                    "summary": "AI analysis temporarily unavailable. Please try again.",
                    "email_draft": ""
                }
                ai_source = "Default (Analysis Unavailable)"

        # Validate and normalize AI response
        ai_analysis = AIAnalysisResult(
            match_score=max(0, min(100, int(ai_result.get("match_score", 0)))),
            key_strengths=ai_result.get("key_strengths", []) or [],
            missing_skills=ai_result.get("missing_skills", []) or [],
            summary=ai_result.get("summary", "") or "",
            email_draft=ai_result.get("email_draft", "") or ""
        )

        logger.info(
            f"Analysis complete [{ai_source}] - {file.filename}: "
            f"Match={ai_analysis.match_score}%"
        )

        return EnhancedResumeAnalysisResponse(
            filename=file.filename,
            text_length=len(extracted_text),
            extracted_text=extracted_text,
            ai_analysis=ai_analysis
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error for {file.filename}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Resume analysis validation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error during resume processing"
        )


@app.post("/analyze-resume/basic", response_model=ResumeAnalysisResponse)
async def analyze_resume_basic(
    file: UploadFile = File(..., description="PDF resume file"),
    job_description: str = Form(..., description="Job description (not used)")
) -> ResumeAnalysisResponse:
    """
    Simple resume text extraction endpoint (legacy/basic mode).
    
    Extracts text from PDF without AI analysis. Useful for testing or
    integration with external analysis systems.

    Process Flow:
    1. Validate uploaded PDF file
    2. Extract text from PDF
    3. Return extracted text only (no AI analysis)

    Args:
        file: PDF resume file (multipart/form-data)
        job_description: Job description (included for API compatibility)
        
    Returns:
        ResumeAnalysisResponse containing:
            - filename: Original uploaded file name
            - text_length: Length of extracted resume text
            - extracted_text: Full resume text from PDF
            
    Raises:
        HTTPException 400: Invalid file format or empty description
        HTTPException 500: Unexpected processing error
    """
    # Validate file is proper PDF
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        logger.warning(f"Invalid file type: {file.content_type} for {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF document. Uploaded file is not a valid PDF."
        )

    if not file.filename.lower().endswith(".pdf"):
        logger.warning(f"Invalid file extension: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File name must end with .pdf extension"
        )

    try:
        # Validate job description
        if not job_description or not job_description.strip():
            raise HTTPException(
                status_code=400,
                detail="Job description cannot be empty or whitespace-only"
            )

        # Read uploaded file into memory stream
        file_content = await file.read()

        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty or cannot be read"
            )

        file_stream = io.BytesIO(file_content)

        # Extract text from PDF
        extracted_text = extract_text_from_pdf(file_stream, file.filename)

        logger.info(f"Extracted {len(extracted_text)} characters from {file.filename}")

        return ResumeAnalysisResponse(
            filename=file.filename,
            text_length=len(extracted_text),
            extracted_text=extracted_text
        )

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error for {file.filename}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Resume extraction failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error processing {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error during PDF extraction"
        )


# ============================================================
# APPLICATION ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import uvicorn

    # Run Uvicorn development server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
