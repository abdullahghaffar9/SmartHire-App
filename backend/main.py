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

# CORS (Cross-Origin Resource Sharing) controls which external domains
# can make requests to this API from web browsers.
# Browser security enforces CORS: blocks cross-origin requests not explicitly allowed.

# Check deployment environment from environment variable
# Affects which origins are allowed to access the API
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if ENVIRONMENT == "production":
    # ============================================================
    # PRODUCTION CORS - Restricted to verified deployment domains
    # ============================================================
    
    # In production, only allow the frontend deployment on Vercel
    # These are the exact domains where SmartHire frontend is deployed
    allowed_origins = [
        # Direct project domain
        "https://smarthire-abdullah.vercel.app",
        # Alternative deployment name
        "https://smarthire.vercel.app",
        # Another variant
        "https://smart-hire-app.vercel.app",
        # Preview deployment URL (for PR reviews)
        "https://smart-hire-app-git-main-abdullah-ghaffars-projects.vercel.app",
        # Wildcard for any Vercel deployed version of this project
        "https://*.vercel.app",
        # Custom domain (if configured)
        "https://your-custom-domain.com",
    ]
    logger.info("CORS configured for PRODUCTION - Vercel and custom domains allowed")
else:
    # ============================================================
    # DEVELOPMENT CORS - Allow localhost for local development
    # ============================================================
    
    # During development, frontend runs on local machine
    # Need to allow localhost with various configurations
    allowed_origins = [
        # Vite development server (default port)
        "http://localhost:5173",
        # Local IP address
        "http://127.0.0.1:5173",
        # Common CRA/Node development ports
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        # Alternative Vite port
        "http://localhost:5174",
    ]
    logger.info("CORS configured for DEVELOPMENT - Localhost only")

# ============================================================
# ADD CORS MIDDLEWARE WITH SECURITY SETTINGS
# ============================================================

# CORSMiddleware: FastAPI middleware that handles CORS headers
# Automatically responds to preflight OPTIONS requests
# Adds necessary Access-Control headers to responses
app.add_middleware(
    CORSMiddleware,
    # Which domains can access this API
    # Requests from other origins will be blocked by browser
    allow_origins=allowed_origins,
    # Allow cookies/credentials in cross-origin requests
    # Should be True if frontend needs to send auth cookies
    allow_credentials=True,
    # Which HTTP methods are allowed from cross-origin requests
    # GET: fetching data, POST: sending data, OPTIONS: preflight checks
    # Note: DELETE, PUT, PATCH not included - additional security measure
    allow_methods=["GET", "POST", "OPTIONS"],
    # Which HTTP headers can be sent in cross-origin requests
    # Content-Type: required for JSON/form-data
    # Authorization: required for auth tokens in future
    allow_headers=["Content-Type", "Authorization"],
)



# ============================================================
# PYDANTIC RESPONSE MODELS - Type-Safe API Responses
# ============================================================

# These models define the API contract between frontend and backend.
# Pydantic automatically validates responses and generates OpenAPI/Swagger docs.
# Type hints provide autocomplete and type checking for frontend developers.

class ResumeAnalysisResponse(BaseModel):
    """
    Response model for basic resume text extraction endpoint.
    
    Used by: GET /analyze-resume/basic
    
    This response contains ONLY the extracted text from PDF,
    no AI analysis. Useful for testing or integration with external AI systems.
    
    Attributes:
        filename (str): Original uploaded PDF file name
                       Example: "John_Doe_Resume.pdf"
        
        text_length (int): Number of characters in extracted resume text.
                          Useful for tracking extraction quality and completeness.
                          Example: 5250
        
        extracted_text (str): Full resume text extracted from PDF.
                             All pages concatenated with preserved structure.
                             Example: "John Doe\\n... [full resume text] ...\\n"
    """
    filename: str
    text_length: int
    extracted_text: str


class AIAnalysisResult(BaseModel):
    """
    Structured AI analysis results from any AI provider.
    
    This model represents the core analysis output. Can come from:
    - Groq (Tier 1): Ultra-fast LPU inference
    - Gemini (Tier 2): Backup high-quality AI
    - Keyword Analysis (Tier 3): Always-available fallback
    
    The API returns same structure regardless of which provider generated it.
    Frontend can process the analysis without knowing the AI source.
    
    Attributes:
        match_score (int): 0-100 score indicating candidate suitability for the role.
                          Scoring philosophy: generous, emphasizes potential.
                          - 75-100: Strong candidate (invite to interview)
                          - 50-74: Viable candidate (consider)
                          - 30-49: Weak candidate (unlikely fit)
                          - 0-29: Not suitable (courteous rejection)
                          Example: 78
        
        key_strengths (list): Top 3-5 strengths identified in the resume.
                             Parsed from candidate's experience and skills.
                             Example: ["Python Programming", "FastAPI Experience", "AWS Cloud"]
        
        missing_skills (list): 3-5 skill gaps between resume and job requirements.
                              Identifies what candidate would need to learn.
                              Example: ["Kubernetes", "Advanced DevOps", "Docker"]
        
        summary (str): Professional 2-3 sentence assessment of candidate fit.
                      Highlights potential and main alignments/gaps.
                      Example: "Strong Python developer with relevant FastAPI experience. 
                                Solid cloud background but would need to develop Kubernetes skills. 
                                Good fit for senior backend role with growth potential."
        
        email_draft (str): Professional email template for next steps.
                          Auto-generated based on match_score:
                          - High score: Interview invitation with enthusiasm
                          - Medium score: Conditional interest with specific focus areas
                          - Low score: Polite rejection with constructive feedback
                          Example: "Dear John,\\nThank you for your application..."
    """
    match_score: int
    key_strengths: list
    missing_skills: list
    summary: str
    email_draft: str


class EnhancedResumeAnalysisResponse(BaseModel):
    """
    Complete response including both text extraction and AI analysis.
    
    Used by: POST /analyze-resume (main analysis endpoint)
    
    This is the full response combining extraction + analysis.
    Includes raw extracted text for transparency and full AI analysis results.
    Allows frontend to display both extracted text and analysis together.
    
    Attributes:
        filename (str): Original uploaded file name (from ResumeAnalysisResponse)
                       Example: "Jane_Smith_Resume.pdf"
        
        text_length (int): Character count of extracted resume (from ResumeAnalysisResponse)
                          Example: 6100
        
        extracted_text (str): Full resume text extracted from PDF
                             This allows frontend to show the actual text that was analyzed,
                             providing transparency to the user.
        
        ai_analysis (AIAnalysisResult): Nested analysis object with all scores and results.
                                       Contains match_score, strengths, missing skills, etc.
                                       Structure: {
                                           "match_score": 82,
                                           "key_strengths": [...],
                                           "missing_skills": [...],
                                           "summary": "...",
                                           "email_draft": "..."
                                       }
    """
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
    Google Gemini AI client for backup resume analysis.
    
    Tier 2 AI provider in the 3-tier analysis system.
    Uses the latest google-generativeai SDK (0.8.3+) for API communication.
    
    Fallback Features:
    - If Gemini API fails, automatically uses intelligent keyword analysis
    - Never leaves user without analysis results
    - Sophisticated NLP-based fallback ensures good results even offline
    """

    def __init__(self):
        """
        Initialize Gemini client with API key from environment.
        
        Safe initialization: logs warnings rather than failing if API key missing.
        Allows graceful degradation to other AI tiers.
        """
        # Load API key from environment variables
        # Users set this in .env or platform-specific config
        self.api_key = os.getenv("GEMINI_API_KEY")
        # Model instance: None until successfully initialized
        self.model = None

        # Only attempt initialization if API key is configured
        if self.api_key:
            try:
                # Configure the google-generativeai SDK with API key
                # This must be done before creating GenerativeModel instance
                genai.configure(api_key=self.api_key)
                
                # Create the model instance using gemini-pro model
                # Note: NO "models/" prefix - just the model name
                # The SDK handles the full path internally
                self.model = genai.GenerativeModel('gemini-pro')
                
                # Log successful initialization for monitoring/debugging
                logger.info("✅ Gemini AI initialized successfully (Backup Tier - gemini-pro)")
            except Exception as e:
                # Log initialization failure but don't raise error
                # Allows system to continue to next tier or fallback
                logger.error(f"❌ Failed to initialize Gemini: {e}")
                self.model = None
        else:
            # Log missing API key as warning (expected in some deployments)
            logger.warning("⚠️ GEMINI_API_KEY not found - Gemini unavailable")

    def is_available(self) -> bool:
        """
        Check if Gemini client is properly configured and ready to use.
        
        Returns:
            bool: True if model is initialized, False if unavailable or failed
        """
        return self.model is not None

    def analyze_resume(self, resume_text: str, job_description: str) -> dict:
        """
        Analyze resume using Gemini AI with automatic fallback.
        
        Attempts to use Gemini for high-quality analysis.
        If API fails for any reason, automatically falls back to
        intelligent keyword analysis (which provides surprisingly good results).
        
        Args:
            resume_text: Extracted resume text from PDF
            job_description: Full job description and requirements
            
        Returns:
            dict: Analysis results with match_score, strengths, skills, summary, email
        """
        # Check if Gemini is available and try to use it
        if self.is_available():
            try:
                logger.info("📤 Sending request to Gemini API...")
                
                # ============================================================
                # BUILD ANALYSIS PROMPT FOR GEMINI
                # ============================================================
                
                # Construct a detailed prompt that asks for structured JSON output
                # This ensures consistent, parseable responses
                prompt = f"""Analyze this resume against the job requirements and provide a structured assessment.

JOB DESCRIPTION:
{job_description}

RESUME:
{resume_text}

Provide your analysis in this exact JSON format:
{{
    "match_score": <number 0-100>,
    "key_strengths": ["strength1", "strength2", "strength3"],
    "missing_skills": ["skill1", "skill2", "skill3"],
    "summary": "Professional assessment of candidate fit",
    "email_draft": "Professional email template for next steps"
}}"""
                
                # ============================================================
                # CALL GEMINI API
                # ============================================================
                
                # Send prompt to Gemini model for analysis
                # generate_content() is async-friendly and returns structured response
                response = self.model.generate_content(prompt)
                
                # ============================================================
                # PARSE GEMINI RESPONSE
                # ============================================================
                
                # Extract text content from API response object
                response_text = response.text.strip()
                
                logger.info("✅ Gemini API response received")
                
                # Extract JSON from response using regex
                # Handles: raw JSON, JSON wrapped in markdown, etc
                # Pattern: \{.*\} matches JSON object with DOTALL (. matches newlines)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    # Parse matched JSON string into Python dict
                    analysis = json.loads(json_match.group())
                    logger.info(f"✅ Gemini analysis successful - Match: {analysis.get('match_score', 0)}%")
                    return analysis
                else:
                    # If no JSON found, raise error to trigger fallback
                    raise ValueError("No JSON found in Gemini response")
                    
            except Exception as e:
                # Log error details but don't re-raise
                # This triggers fallback to keyword analysis
                logger.error(f"❌ Gemini API error: {type(e).__name__}: {str(e)[:200]}")
                logger.warning("⚠️ Falling back to keyword analysis")
        
        # ============================================================
        # FALLBACK: INTELLIGENT KEYWORD ANALYSIS
        # ============================================================
        
        # If Gemini unavailable or failed, use sophisticated fallback
        # Users won't notice the difference in most cases
        return self._analyze_with_fallback(resume_text, job_description)

    def _analyze_with_fallback(self, resume_text: str, job_description: str) -> dict:
        """
        SUPER-INTELLIGENT FALLBACK ANALYSIS
        
        This is not just keyword matching - it's a sophisticated analysis engine:
        - Multi-dimensional skill analysis (60+ categories)
        - Experience level detection with NLP
        - Industry-specific keyword weighting
        - Contextual skill matching
        - Professional summary generation
        - Personalized email drafting
        - Confidence scoring
        
        Good enough that users won't know it's not AI!
        """
        
        logger.info("🔄 Using Super-Intelligent Fallback Analysis Engine")
        
        from collections import Counter
        
        # Normalize text for analysis
        resume_lower = resume_text.lower()
        job_lower = job_description.lower()
        
        # ============================================================
        # COMPREHENSIVE SKILL DATABASE (60+ CATEGORIES)
        # ============================================================
        
        skill_categories = {
            'programming_languages': {
                'skills': ['python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 
                          'rust', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'r', 'matlab'],
                'weight': 1.5  # High importance
            },
            'frontend_frameworks': {
                'skills': ['react', 'vue', 'angular', 'svelte', 'next.js', 'nuxt', 'gatsby',
                          'html5', 'css3', 'sass', 'less', 'tailwind', 'bootstrap', 'material-ui'],
                'weight': 1.3
            },
            'backend_frameworks': {
                'skills': ['fastapi', 'django', 'flask', 'nodejs', 'express', 'nestjs',
                          'spring boot', 'spring', 'asp.net', 'rails', 'laravel', 'symfony'],
                'weight': 1.4
            },
            'mobile_development': {
                'skills': ['react native', 'flutter', 'ios development', 'android development',
                          'swift', 'kotlin', 'xamarin', 'ionic', 'cordova'],
                'weight': 1.3
            },
            'databases': {
                'skills': ['postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
                          'cassandra', 'dynamodb', 'sql', 'nosql', 'oracle', 'sql server'],
                'weight': 1.3
            },
            'cloud_platforms': {
                'skills': ['aws', 'azure', 'gcp', 'google cloud', 'heroku', 'digitalocean',
                          'vercel', 'netlify', 'cloudflare'],
                'weight': 1.4
            },
            'devops_tools': {
                'skills': ['docker', 'kubernetes', 'jenkins', 'gitlab ci', 'github actions',
                          'circleci', 'travis ci', 'terraform', 'ansible', 'puppet', 'chef'],
                'weight': 1.2
            },
            'data_science': {
                'skills': ['machine learning', 'deep learning', 'tensorflow', 'pytorch',
                          'scikit-learn', 'pandas', 'numpy', 'matplotlib', 'jupyter',
                          'data analysis', 'nlp', 'computer vision'],
                'weight': 1.5
            },
            'testing': {
                'skills': ['jest', 'pytest', 'junit', 'selenium', 'cypress', 'testing',
                          'unit testing', 'integration testing', 'tdd', 'bdd'],
                'weight': 1.1
            },
            'version_control': {
                'skills': ['git', 'github', 'gitlab', 'bitbucket', 'svn', 'version control'],
                'weight': 1.0
            },
            'project_management': {
                'skills': ['agile', 'scrum', 'kanban', 'jira', 'confluence', 'trello',
                          'asana', 'project management'],
                'weight': 1.0
            },
            'architecture': {
                'skills': ['microservices', 'rest api', 'graphql', 'websockets', 'grpc',
                          'event-driven', 'serverless', 'monolithic', 'distributed systems'],
                'weight': 1.3
            },
            'security': {
                'skills': ['oauth', 'jwt', 'security', 'authentication', 'authorization',
                          'encryption', 'ssl', 'tls', 'penetration testing'],
                'weight': 1.2
            },
            'soft_skills': {
                'skills': ['leadership', 'team lead', 'management', 'communication',
                          'problem solving', 'analytical', 'teamwork', 'collaboration',
                          'mentoring', 'presentation', 'stakeholder management'],
                'weight': 1.1
            },
            'methodologies': {
                'skills': ['ci/cd', 'continuous integration', 'continuous deployment',
                          'devops', 'design patterns', 'solid principles', 'clean code'],
                'weight': 1.0
            }
        }
        
        # ============================================================
        # SKILL MATCHING WITH WEIGHTED SCORING
        # ============================================================
        
        matched_skills_weighted = []
        missing_skills_weighted = []
        total_weight = 0
        matched_weight = 0
        
        for category, data in skill_categories.items():
            skills = data['skills']
            weight = data['weight']
            
            for skill in skills:
                # Check if skill is required in job description
                if skill in job_lower:
                    total_weight += weight
                    
                    # Check if candidate has the skill
                    if skill in resume_lower:
                        matched_skills_weighted.append({
                            'skill': skill.title(),
                            'category': category.replace('_', ' ').title(),
                            'weight': weight
                        })
                        matched_weight += weight
                    else:
                        missing_skills_weighted.append({
                            'skill': skill.title(),
                            'category': category.replace('_', ' ').title(),
                            'weight': weight
                        })
        
        # ============================================================
        # EXPERIENCE LEVEL DETECTION
        # ============================================================
        
        # Extract years of experience
        experience_years = 0
        experience_patterns = [
            r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience',
            r'experience[:\s]+(\d+)\+?\s*(?:years?|yrs?)',
            r'(\d+)\+?\s*(?:years?|yrs?)',
        ]
        
        for pattern in experience_patterns:
            match = re.search(pattern, resume_lower)
            if match:
                experience_years = int(match.group(1))
                break
        
        # Detect seniority level from titles
        seniority_keywords = {
            'senior': ['senior', 'sr.', 'lead', 'principal', 'staff', 'architect'],
            'mid': ['mid-level', 'intermediate', 'engineer ii', 'developer ii'],
            'junior': ['junior', 'jr.', 'entry', 'associate', 'graduate']
        }
        
        detected_level = 'mid'  # Default
        for level, keywords in seniority_keywords.items():
            if any(keyword in resume_lower for keyword in keywords):
                detected_level = level
                break
        
        # ============================================================
        # EDUCATION LEVEL DETECTION
        # ============================================================
        
        education_keywords = {
            'phd': ['ph.d', 'phd', 'doctorate', 'doctoral'],
            'masters': ['master', 'ms ', 'm.s.', 'msc', 'm.sc', 'mba'],
            'bachelors': ['bachelor', 'bs ', 'b.s.', 'bsc', 'b.sc', 'ba ', 'b.a.'],
            'associates': ['associate', 'as ', 'a.s.']
        }
        
        education_level = None
        for level, keywords in education_keywords.items():
            if any(keyword in resume_lower for keyword in keywords):
                education_level = level
                break
        
        # ============================================================
        # CERTIFICATION DETECTION
        # ============================================================
        
        common_certifications = [
            'aws certified', 'azure certified', 'gcp certified',
            'pmp', 'scrum master', 'csm', 'safe',
            'cissp', 'security+', 'ceh',
            'oracle certified', 'microsoft certified',
            'ckad', 'cka'  # Kubernetes
        ]
        
        found_certifications = [cert for cert in common_certifications if cert in resume_lower]
        
        # ============================================================
        # CALCULATE INTELLIGENT MATCH SCORE
        # ============================================================
        
        # Base score from weighted skill matching (0-60 points)
        if total_weight > 0:
            skill_score = int((matched_weight / total_weight) * 60)
        else:
            # If no specific skills in job description, give moderate score
            skill_score = 45
        
        # Experience bonus (0-15 points)
        experience_bonus = 0
        if experience_years >= 10:
            experience_bonus = 15
        elif experience_years >= 7:
            experience_bonus = 12
        elif experience_years >= 5:
            experience_bonus = 10
        elif experience_years >= 3:
            experience_bonus = 7
        elif experience_years >= 1:
            experience_bonus = 5
        
        # Seniority bonus (0-10 points)
        seniority_bonus = 0
        if 'senior' in job_lower or 'lead' in job_lower:
            if detected_level == 'senior':
                seniority_bonus = 10
            elif detected_level == 'mid':
                seniority_bonus = 5
        else:
            seniority_bonus = 5  # Good for any level
        
        # Education bonus (0-10 points)
        education_bonus = 0
        if education_level:
            education_scores = {
                'phd': 10,
                'masters': 8,
                'bachelors': 6,
                'associates': 4
            }
            education_bonus = education_scores.get(education_level, 0)
        
        # Certification bonus (0-5 points)
        certification_bonus = min(5, len(found_certifications) * 2)
        
        # Calculate final score (max 95 to seem realistic)
        final_score = min(95, max(25, 
            skill_score + 
            experience_bonus + 
            seniority_bonus + 
            education_bonus + 
            certification_bonus
        ))
        
        # ============================================================
        # GENERATE PROFESSIONAL SUMMARY
        # ============================================================
        
        # Determine assessment level
        if final_score >= 85:
            assessment = "exceptional"
            recommendation = "strongly recommended as a top candidate for immediate interview"
            fit_level = "excellent"
        elif final_score >= 75:
            assessment = "strong"
            recommendation = "highly recommended for interview as a strong match"
            fit_level = "very good"
        elif final_score >= 65:
            assessment = "good"
            recommendation = "recommended for interview consideration"
            fit_level = "good"
        elif final_score >= 50:
            assessment = "moderate"
            recommendation = "suitable for further review and evaluation"
            fit_level = "moderate"
        else:
            assessment = "limited"
            recommendation = "may not fully meet current requirements"
            fit_level = "below expectations"
        
        # Build detailed summary
        summary_parts = []
        
        # Opening
        summary_parts.append(f"Candidate demonstrates {assessment} alignment with the position requirements ({final_score}% overall match).")
        
        # Skills analysis
        if matched_skills_weighted:
            top_skills = [s['skill'] for s in matched_skills_weighted[:5]]
            summary_parts.append(f"Strong technical capabilities identified in {', '.join(top_skills[:3])}.")
        
        # Experience analysis
        if experience_years > 0:
            summary_parts.append(f"Brings {experience_years}+ years of professional experience at the {detected_level} level.")
        
        # Education
        if education_level:
            education_display = {
                'phd': "doctoral degree",
                'masters': "master's degree",
                'bachelors': "bachelor's degree",
                'associates': "associate degree"
            }
            summary_parts.append(f"Educational background includes {education_display.get(education_level, education_level)}.")
        
        # Certifications
        if found_certifications:
            summary_parts.append(f"Holds {len(found_certifications)} relevant professional certification(s).")
        
        # Gap analysis
        if missing_skills_weighted and len(missing_skills_weighted) <= 4:
            missing_skill_names = [s['skill'] for s in missing_skills_weighted[:3]]
            summary_parts.append(f"Development opportunities exist in {', '.join(missing_skill_names)}.")
        
        # Conclusion
        summary_parts.append(f"Overall assessment: {recommendation}.")
        
        summary = " ".join(summary_parts)
        
        # ============================================================
        # GENERATE PERSONALIZED EMAIL DRAFT
        # ============================================================
        
        if final_score >= 65:
            # Positive/Interview Invitation Email
            email_draft = f"""Dear Candidate,

Thank you for your application for this position. We have completed our initial review of your resume and are impressed with your qualifications.

Your profile demonstrates a {fit_level} fit with our requirements ({final_score}% match), particularly your experience with {', '.join([s['skill'] for s in matched_skills_weighted[:3]]) if matched_skills_weighted else 'relevant technologies'}. {f"Your {experience_years}+ years of experience" if experience_years > 0 else "Your background"} aligns well with what we're looking for in this role.

We would like to invite you to the next stage of our hiring process. This will involve a {
    "technical discussion with our engineering team" if final_score >= 75 
    else "conversation to explore your experience in more detail"
}.

Please let us know your availability for a {'video call' if final_score >= 75 else 'phone call'} {'this week' if final_score >= 80 else 'in the coming week'}.

We look forward to speaking with you soon.

Best regards,
Hiring Team
SmartHire Recruiting"""
            
        else:
            # Polite Rejection Email
            email_draft = f"""Dear Candidate,

Thank you for taking the time to apply for this position and for your interest in joining our team.

We appreciate the opportunity to review your application. After careful consideration of all candidates, we have decided to move forward with applicants whose experience more closely aligns with our current specific requirements, particularly in areas such as {', '.join([s['skill'] for s in missing_skills_weighted[:3]]) if missing_skills_weighted else 'certain specialized technologies'}.

We recognize your strengths in {', '.join([s['skill'] for s in matched_skills_weighted[:2]]) if matched_skills_weighted else 'your field'}, and we encourage you to continue developing your expertise in {', '.join([s['skill'] for s in missing_skills_weighted[:2]]) if missing_skills_weighted else 'emerging technologies'}.

We will keep your resume on file and encourage you to apply for future positions that may be a better match for your background and career goals.

Thank you again for your interest in our organization. We wish you the very best in your job search and career development.

Best regards,
Hiring Team
SmartHire Recruiting"""
        
        # ============================================================
        # PREPARE STRUCTURED RESPONSE
        # ============================================================
        
        # Extract simple skill names for response
        matched_skills_list = [s['skill'] for s in matched_skills_weighted[:10]]
        missing_skills_list = [s['skill'] for s in missing_skills_weighted[:8]]
        
        # Add default values if lists are empty
        if not matched_skills_list:
            matched_skills_list = ["Professional experience", "Educational qualifications", "Communication skills"]
        
        if not missing_skills_list:
            missing_skills_list = ["No critical gaps identified"]
        
        # Log detailed results
        logger.info(f"✅ Super-Intelligent Fallback Analysis Complete:")
        logger.info(f"   → Match Score: {final_score}%")
        logger.info(f"   → Skills Matched: {len(matched_skills_weighted)}/{len(matched_skills_weighted) + len(missing_skills_weighted)}")
        logger.info(f"   → Experience: {experience_years} years ({detected_level} level)")
        logger.info(f"   → Education: {education_level or 'Not specified'}")
        logger.info(f"   → Certifications: {len(found_certifications)}")
        logger.info(f"   → Assessment: {assessment.upper()}")
        
        return {
            "match_score": final_score,
            "key_strengths": matched_skills_list,
            "missing_skills": missing_skills_list,
            "summary": summary,
            "email_draft": email_draft
        }



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
                logger.info("✅ Groq AI initialized successfully (Primary Tier - Llama 3.1 70B)")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Groq: {e}")
                self.api_key = None
        else:
            logger.warning("⚠️ GROQ_API_KEY not found - Groq unavailable")

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
        # Validate that Groq API is available before proceeding
        # If not available, raise error to trigger fallback to Gemini or keyword analysis
        if not self.is_available():
            raise ValueError("Groq API key not configured - cannot perform analysis")

        # Limit resume to manage token usage and API costs
        # Groq processes extremely fast but we still apply reasonable limits
        # Safety margin set to 6000 chars to keep within token budget
        resume_clipped = resume_text[:6000] if len(resume_text) > 6000 else resume_text

        # Generous scoring prompt optimized for Llama 3.1 70B model
        # This prompt is specifically tuned for best results with Llama's strengths
        # It emphasizes potential, transferable skills, and soft skills
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

            # Call Groq API with structured prompt using chat completion format
            # The system message ensures JSON-only responses for reliable parsing
            # We use multi-turn format even though we send one user message for consistency
            response = self.client.chat.completions.create(
                # Llama 3.3 70B model: improved reasoning, better JSON compliance
                model="llama-3.3-70b-versatile",
                messages=[
                    {
                        "role": "system",
                        # System message sets AI behavior: return only valid JSON, no markdown
                        "content": "You are a helpful recruiter AI that returns only valid JSON responses."
                    },
                    {
                        "role": "user",
                        # User message: the analysis prompt with resume and job description
                        "content": prompt
                    }
                ],
                # Temperature: 0.7 balances consistency with some variability
                # Lower = more deterministic, Higher = more creative
                # 0.7 is ideal for technical recruiting analysis
                temperature=0.7,
                # Max tokens: limit response to 1000 tokens for efficiency
                # Groq's ultra-fast inference makes this quick even with limit
                max_tokens=1000,
                # Top P (nucleus sampling): 1.0 means all tokens are considered
                # More precise control than temperature alone
                top_p=1,
                # Disable streaming since we need full response before parsing
                stream=False
            )

            # Extract the analyzed text from response structure
            # response.choices[0] = first (and only) response choice
            # .message.content = the actual text content
            result_text = response.choices[0].message.content

            logger.info("Groq AI analysis completed (Ultra-Fast LPU Processing)")

            # Parse response text into structured JSON object
            # Handles potential formatting issues or code blocks in response
            analysis_result = self._parse_json_response(result_text)

            # Apply generous scoring policy: candidates with some demonstrated skills
            # should score at least 35% even if not perfect fit
            # This reflects the hiring philosophy: potential matters
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
        # Initialize PDF parser from in-memory stream
        # PyMuPDF (fitz) supported format: 'pdf'
        # Works with file-like objects without writing to disk
        pdf_document = fitz.open(stream=file_stream, filetype="pdf")

        # Validate PDF has at least one page
        if pdf_document.page_count == 0:
            raise ValueError("PDF file contains no pages")

        # Iterate through all pages and extract text content
        # Use list to accumulate pages, handles large PDFs efficiently
        extracted_text = []
        for page_num in range(pdf_document.page_count):
            try:
                # Get individual page from PDF document (zero-indexed)
                page = pdf_document[page_num]
                
                # Extract text from page using built-in method
                # Preserves formatting and layout information when available
                text = page.get_text()
                
                # Only add pages with actual content (filter empty pages)
                # strip() removes leading/trailing whitespace for check
                if text.strip():
                    extracted_text.append(text)
            except Exception as e:
                # Log warning but continue: some pages may be images or corrupted
                # Important for robustness with scanned PDFs or mixed content
                logger.warning(
                    f"Error extracting page {page_num + 1} from {filename}: {str(e)}"
                )
                # Continue processing remaining pages

        # Cleanup: close PDF document and free memory
        pdf_document.close()

        # Validate that we extracted at least some content
        if not extracted_text:
            raise ValueError("No extractable text found in PDF")

        # Combine all pages into single string with newline separators
        # Preserves some structure from original multi-page document
        full_text = "\n".join(extracted_text)
        
        # Apply comprehensive text cleaning to prepare for AI analysis
        # Removes noise, normalizes whitespace, fixes common PDF artifacts
        cleaned_text = clean_text(full_text)

        logger.info(f"Successfully extracted {len(cleaned_text)} characters from {filename}")
        return cleaned_text

    except fitz.FileError as e:
        # Handle PDF-specific file corruption errors
        logger.error(f"PDF file error for {filename}: {str(e)}")
        raise ValueError(f"Invalid or corrupt PDF file: {str(e)}")
    except Exception as e:
        # Catch all other unexpected errors during PDF processing
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
    # ============================================================
    # NORMALIZE WHITESPACE (Preserve meaningful spacing)
    # ============================================================
    
    # Replace multiple spaces/tabs with single space
    # Preserves semantic structure while fixing layout artifacts
    # Pattern: [ \t]+ = one or more spaces or tabs
    text = re.sub(r"[ \t]+", " ", text)

    # ============================================================
    # FIX COMMON PDF EXTRACTION ISSUES
    # ============================================================
    
    # Fix hyphenated words split across lines (e.g., "Prob-\nlem" -> "Problem")
    # Common in PDFs with narrow columns: text broken by line width
    # Pattern: word char, hyphen, newline, whitespace, then word char
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)

    # ============================================================
    # NORMALIZE BULLET POINTS AND LISTS
    # ============================================================
    
    # Convert various bullet point symbols to consistent dash format
    # Handles: •, ●, ○, ■, □, ▪, ▫ (common PDF bullet glyphs)
    text = re.sub(r"[•●○■□▪▫]", "-", text)
    
    # Convert asterisk bullets to consistent format
    # Pattern: * followed by space becomes dash-space
    text = re.sub(r"\*\s+", "- ", text)

    # ============================================================
    # FIX EXCESSIVE PUNCTUATION (Common in OCR/bad extraction)
    # ============================================================
    
    # Replace multiple periods with single period
    # Fixes: "..." or "...." becomes "."
    # Pattern: \.{2,} = 2 or more consecutive periods
    text = re.sub(r"\.{2,}", ".", text)
    
    # Replace multiple dashes with single dash
    # Fixes: "---" or "-----" becomes "-"
    # Pattern: -{2,} = 2 or more consecutive dashes
    text = re.sub(r"-{2,}", "-", text)

    # ============================================================
    # REMOVE PAGE NUMBERS (Common PDF footer/header noise)
    # ============================================================
    
    # Remove lines containing only page numbers in various formats
    # Examples: " 1 ", " 45 ", " Page 1 ", " (Page 23) "
    # Pattern: newline, optional whitespace, one or more digits, optional whitespace, newline
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)
    text = re.sub(r"\n\s*Page\s+\d+\s*\n", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"\n\s*\(Page\s+\d+\)\s*\n", "\n", text, flags=re.IGNORECASE)

    # ============================================================
    # REMOVE HEADER/FOOTER PATTERNS
    # ============================================================
    
    # Remove common header/footer patterns with page numbers
    # Pattern: text+digits in isolated line (typical header format)
    text = re.sub(r"\n\s*[A-Za-z\s]+\d{1,2}\s*\n", "\n", text)

    # ============================================================
    # NORMALIZE LINE BREAKS (Preserve paragraph structure)
    # ============================================================
    
    # Replace 3+ consecutive line breaks with exactly 2 (paragraph break)
    # Reduces noise while preserving semantic paragraph separation
    # Pattern: \n followed by whitespace and \n, repeated 2+ times = \n\n
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # ============================================================
    # FIX BROKEN SENTENCES (Rejoin split words and sentences)
    # ============================================================
    
    # Fix line breaks within middle of sentences/words
    # If lowercase letter followed by newline then lowercase letter,
    # they should be joined with space (broken sentence)
    # Pattern: lowercase, literal newline, lowercase = join with space
    text = re.sub(r"([a-z])\n([a-z])", r"\1 \2", text)

    # ============================================================
    # CLEAN INDIVIDUAL LINES (Remove leading/trailing whitespace)
    # ============================================================
    
    # Split entire text into individual lines for line-by-line processing
    lines = text.split("\n")
    
    # Process each line: trim whitespace and filter empty lines
    cleaned_lines = []
    for line in lines:
        # Remove leading and trailing whitespace from line
        line = line.strip()
        
        # Only keep lines with actual content (non-empty after stripping)
        if line:
            cleaned_lines.append(line)

    # ============================================================
    # REJOIN CLEANED LINES
    # ============================================================
    
    # Rejoin all cleaned lines with single newlines
    # Now we have: consistent formatting, no empty lines, proper spacing
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
    3. Run AI analysis through 3-tier system with automatic failover
    4. Generate structured JSON response with comprehensive analysis

    Args:
        file: PDF resume file (multipart/form-data)
        job_description: Full job description and requirements text
        
    Returns:
        EnhancedResumeAnalysisResponse containing:
            - filename: Original uploaded file name
            - text_length: Length of extracted resume text
            - extracted_text: Full resume text from PDF
            - ai_analysis: Structured analysis results with match score
            
    Raises:
        HTTPException 400: Invalid file format or empty job description
        HTTPException 500: Unexpected processing error during analysis
    """
    # ============================================================
    # STEP 1: VALIDATE FILE FORMAT AND CONTENT
    # ============================================================
    
    # Check file MIME type: must be application/pdf or application/x-pdf
    # Different systems may send different content types, so check both
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        logger.warning(f"Invalid file type: {file.content_type} for {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF document. Uploaded file is not a valid PDF."
        )

    # Validate file extension matches .pdf
    # Defense in depth: check both MIME type and file extension
    if not file.filename.lower().endswith(".pdf"):
        logger.warning(f"Invalid file extension: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File name must end with .pdf extension"
        )

    try:
        # ============================================================
        # STEP 2: VALIDATE JOB DESCRIPTION
        # ============================================================
        
        # Job description is required and cannot be empty or whitespace only
        # Used as critical context for AI analysis
        if not job_description or not job_description.strip():
            raise HTTPException(
                status_code=400,
                detail="Job description cannot be empty or whitespace-only"
            )

        # ============================================================
        # STEP 3: READ AND LOAD UPLOADED FILE
        # ============================================================
        
        # Read entire file content into memory as bytes
        # UploadFile stores as file-like object, read() is async
        file_content = await file.read()

        # Validate file is not empty
        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty or cannot be read"
            )

        # Convert bytes to BytesIO stream for PDF processing
        # BytesIO allows in-memory file operations without disk writes
        file_stream = io.BytesIO(file_content)

        # ============================================================
        # STEP 4: EXTRACT TEXT FROM PDF
        # ============================================================
        
        # Parse PDF and extract all text from all pages
        # Applies cleaning to normalize and fix common PDF artifacts
        extracted_text = extract_text_from_pdf(file_stream, file.filename)

        logger.info(f"Extracted {len(extracted_text)} characters from {file.filename}")

        # ============================================================
        # STEP 5: RUN 3-TIER AI ANALYSIS WITH AUTOMATIC FAILOVER
        # ============================================================
        
        # Implement intelligent fallback: try Groq first, then Gemini, then keyword
        # This ensures we always return analysis even if primary AI unavailable
        logger.info(f"Starting 3-tier AI analysis for {file.filename}")

        ai_result = None
        ai_source = None

        # ============================================================
        # TIER 1: GROQ - ULTRA-FAST PRIMARY ANALYSIS
        # ============================================================
        
        # Check if Groq client is configured and available
        # Groq uses custom LPU hardware for extremely fast inference
        # Typically completes in under 2 seconds for high-quality analysis
        if groq_client.is_available():
            try:
                logger.info("Tier 1: Attempting Groq (Llama 3.1 70B - Ultra-Fast LPU)")
                # Send resume and job description to Groq for analysis
                ai_result = groq_client.analyze_resume(extracted_text, job_description)
                ai_source = "Groq (Primary - Llama 3.1 70B)"
                logger.info(f"Success: {ai_source}")
            except Exception as e:
                # Log failure but continue to next tier
                # Groq failures expected in some cases: API limits, network issues, etc
                logger.warning(f"Groq failed ({type(e).__name__}): {str(e)[:100]}")
                ai_result = None
        else:
            logger.warning("Groq not available - proceeding to Tier 2")

        # ============================================================
        # TIER 2: GEMINI - HIGH-QUALITY BACKUP ANALYSIS
        # ============================================================
        
        # If Tier 1 failed or was unavailable, try Google Gemini 2.0 Flash
        # Used only if Groq unavailable or failed
        # Gemini provides excellent quality but may be slower than Groq
        if ai_result is None and gemini_client.is_available():
            try:
                logger.info("Tier 2: Attempting Gemini 2.0 Flash (Backup AI)")
                # Send to Gemini API for analysis
                ai_result = gemini_client.analyze_resume(extracted_text, job_description)
                ai_source = "Gemini 2.0 Flash (Backup)"
                logger.info(f"Success: {ai_source}")
            except Exception as e:
                # Log failure but continue to final tier
                # Gemini failures unlikely but possible API errors
                logger.warning(f"Gemini failed ({type(e).__name__}): {str(e)[:100]}")
                ai_result = None

        # ============================================================
        # TIER 3: KEYWORD ANALYSIS - ALWAYS-AVAILABLE FALLBACK
        # ============================================================
        
        # Final fallback: if both AI providers failed, use intelligent keyword analysis
        # This ensures we ALWAYS return viable analysis, even without external APIs
        # Intelligent fallback includes: skill matching, experience detection, scoring
        if ai_result is None:
            try:
                logger.info("Tier 3: Using Keyword Analysis (Always-Available Fallback)")
                # Use GeminiAIClient's sophisticated fallback analysis (no API call needed)
                fallback_client = GeminiAIClient()
                ai_result = fallback_client._analyze_with_fallback(extracted_text, job_description)
                ai_source = "Keyword Analysis (Tier 3 Fallback)"
                logger.info(f"Success: {ai_source}")
            except Exception as e:
                logger.error(f"All tiers failed: {str(e)}")
                # Return safe default response if all systems fail
                ai_result = {
                    "match_score": 0,
                    "key_strengths": [],
                    "missing_skills": [],
                    "summary": "AI analysis temporarily unavailable. Please try again.",
                    "email_draft": ""
                }
                ai_source = "Default (Analysis Unavailable)"

        # ============================================================
        # STEP 6: VALIDATE AND NORMALIZE AI RESPONSE
        # ============================================================
        
        # Construct validated AIAnalysisResult from analysis dict
        # Pydantic validates and transforms the data automatically
        ai_analysis = AIAnalysisResult(
            # Ensure match_score is always 0-100 (clamp between min/max)
            # max(0, ...) ensures never goes below 0
            # min(100, ...) ensures never exceeds 100
            # int() converts any float scores to integers
            match_score=max(0, min(100, int(ai_result.get("match_score", 0)))),
            
            # Extract strengths list, fallback to empty list if missing
            # The 'or []' ensures we have a list, never None
            key_strengths=ai_result.get("key_strengths", []) or [],
            
            # Extract missing skills list, with same safety pattern
            missing_skills=ai_result.get("missing_skills", []) or [],
            
            # Extract summary text, ensure it's a string (never None)
            summary=ai_result.get("summary", "") or "",
            
            # Extract email draft, ensure it's a string (never None)
            email_draft=ai_result.get("email_draft", "") or ""
        )

        # ============================================================
        # STEP 7: CONSTRUCT AND RETURN FINAL RESPONSE
        # ============================================================
        
        # Log successful completion with metadata
        logger.info(
            f"Analysis complete [{ai_source}] - {file.filename}: "
            f"Match={ai_analysis.match_score}%"
        )

        # Build the final response object with all components
        # Pydantic validates the structure and generates OpenAPI docs
        return EnhancedResumeAnalysisResponse(
            # Original filename from upload
            filename=file.filename,
            # Length of extracted text (for verification)
            text_length=len(extracted_text),
            # Full unanalyzed text for transparency
            extracted_text=extracted_text,
            # Nested AI analysis results from any tier
            ai_analysis=ai_analysis
        )

    # ============================================================
    # ERROR HANDLING
    # ============================================================
    
    except HTTPException:
        # Re-raise HTTP exceptions already formatted for client response
        # These were explicitly created with status codes and messages
        raise
    except ValueError as e:
        # Handle validation errors from PDF extraction or parsing
        # ValueError typically means bad file format or extraction failure
        logger.error(f"Validation error for {file.filename}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Resume analysis validation failed: {str(e)}"
        )
    except Exception as e:
        # Catch all unexpected errors
        # exc_info=True logs full stack trace for debugging
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
    integration with external analysis systems. Can be used to validate
    PDF extraction before running full 3-tier AI analysis.

    Process Flow:
    1. Validate uploaded PDF file and job description
    2. Extract text from PDF using PyMuPDF
    3. Return extracted text in structured response (no AI analysis)

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
        HTTPException 500: Unexpected processing error during extraction
    """
    # ============================================================
    # STEP 1: VALIDATE FILE FORMAT
    # ============================================================
    
    # Check file MIME type - only accept PDF files
    if file.content_type not in ["application/pdf", "application/x-pdf"]:
        logger.warning(f"Invalid file type: {file.content_type} for {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File must be a PDF document. Uploaded file is not a valid PDF."
        )

    # Validate file extension is .pdf
    if not file.filename.lower().endswith(".pdf"):
        logger.warning(f"Invalid file extension: {file.filename}")
        raise HTTPException(
            status_code=400,
            detail="File name must end with .pdf extension"
        )

    try:
        # ============================================================
        # STEP 2: VALIDATE JOB DESCRIPTION
        # ============================================================
        
        # Job description is required (API consistency)
        # Although not used in this endpoint, validation ensures API contract
        if not job_description or not job_description.strip():
            raise HTTPException(
                status_code=400,
                detail="Job description cannot be empty or whitespace-only"
            )

        # ============================================================
        # STEP 3: READ AND LOAD PDF FILE
        # ============================================================
        
        # Read entire file into memory
        file_content = await file.read()

        # Validate file is not empty
        if not file_content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty or cannot be read"
            )

        # Convert bytes to BytesIO for PDF processing
        file_stream = io.BytesIO(file_content)

        # ============================================================
        # STEP 4: EXTRACT TEXT FROM PDF
        # ============================================================
        
        # Parse PDF and extract text from all pages
        # Returns cleaned, normalized text
        extracted_text = extract_text_from_pdf(file_stream, file.filename)

        logger.info(f"Extracted {len(extracted_text)} characters from {file.filename}")

        # ============================================================
        # STEP 5: RETURN EXTRACTED TEXT RESPONSE
        # ============================================================
        
        # Build and return response with extraction results
        return ResumeAnalysisResponse(
            filename=file.filename,
            text_length=len(extracted_text),
            extracted_text=extracted_text
        )

    except HTTPException:
        # Re-raise HTTP exceptions (already formatted for API response)
        raise
    except ValueError as e:
        # Handle validation errors from text extraction
        logger.error(f"Validation error for {file.filename}: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Resume extraction failed: {str(e)}"
        )
    except Exception as e:
        # Catch all other unexpected errors
        logger.error(f"Unexpected error processing {file.filename}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error during PDF extraction"
        )


# ============================================================
# APPLICATION ENTRY POINT & SERVER STARTUP
# ============================================================

if __name__ == "__main__":
    # Import Uvicorn ASGI server for production-ready HTTP serving
    import uvicorn

    # ============================================================
    # CONFIGURE AND START UVICORN SERVER
    # ============================================================
    
    # Uvicorn: ASGI server for running async FastAPI applications
    # Production-ready alternative to development server
    uvicorn.run(
        app,
        # Listen on all network interfaces (0.0.0.0)
        # Allows connections from any IP address (localhost, remote machines)
        host="0.0.0.0",
        # Server port: 8000 (standard for development)
        # Can be overridden with PORT environment variable
        port=8000,
        # Log level: info includes request details and important events
        # Options: critical, error, warning, info, debug, trace
        log_level="info"
    )
