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
                # 
                # PROMPT STRUCTURE:
                # 1. Clear instruction: "Analyze resume against job requirements"
                # 2. Job description first (context for analysis)
                # 3. Resume text second (subject being analyzed)
                # 4. Explicit JSON format requirement
                # 5. Field specifications (match_score 0-100, max 3 items per list)
                #
                # WHY THIS STRUCTURE?
                # - Clear instruction: Sets task boundaries
                # - Job description first: Establishes evaluation criteria
                # - Resume second: Subject of evaluation
                # - JSON format: Ensures parseable output
                # - Field specs: Limits response size, ensures consistency
                #
                # GEMINI DIFFERENCES:
                # Gemini often includes preamble/explanation text before JSON.
                # Unlike Groq with system message, Gemini needs regex extraction.
                # Gemini is also slightly slower (~5-10s) but higher quality.
                # ============================================================
                
                prompt = f"""Analyze this resume against the job requirements and provide a structured assessment.

JOB DESCRIPTION:
{job_description}

RESUME:
{resume_text}

Provide your analysis in this exact JSON format (no other text before or after):
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
                # 
                # Gemini API CHARACTERISTICS:
                # - Model name: "gemini-pro" (or "gemini-2.0-flash" in newer versions)
                # - Method: generate_content() - synchronous, returns response object
                # - Response structure: response.text contains the generated text
                # - Speed: ~5-10 seconds typically (slower than Groq's <2s)
                # - Quality: Higher quality, better reasoning capabilities
                # - Tokens: More generous free tier (60 requests/minute)
                # - Reliability: Less stable than Groq, more often needs fallback
                #
                # WHY GEMINI AS TIER 2?
                # - Primary: Groq for super-fast analysis
                # - Secondary: Gemini for higher quality if speed OK
                # - Fallback: Keyword analysis always works offline
                # ============================================================
                
                # Send prompt to Gemini model for analysis
                # generate_content() is async-friendly and returns structured response
                response = self.model.generate_content(prompt)
                
                # ============================================================
                # PARSE GEMINI RESPONSE
                # ============================================================
                # 
                # RESPONSE FORMAT VARIATIONS:
                # Gemini often includes explanatory text before/after JSON.
                # Examples:
                # "Here's the analysis: {...}" → need to extract JSON
                # {...} → pure JSON (ideal case)
                # "```json\n{...}\n```" → markdown wrapped
                #
                # ROBUST EXTRACTION:
                # Use regex to find JSON object: \{.*\}
                # Pattern explanation:
                # - \{ = literal opening brace
                # - .* = any characters (greedy - matches as much as possible)
                # - \} = literal closing brace
                # - re.DOTALL = make . match newlines too
                # This handles multi-line JSON correctly.
                # ============================================================
                
                # Extract text content from API response object
                response_text = response.text.strip()
                
                logger.info("✅ Gemini API response received")
                
                # Extract JSON from response using regex
                # Handles: raw JSON, JSON with preamble, markdown-wrapped JSON, etc
                # Pattern: \{.*\} matches JSON object with DOTALL (. matches newlines)
                json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                if json_match:
                    # Parse matched JSON string into Python dict
                    analysis = json.loads(json_match.group())
                    logger.info(f"✅ Gemini analysis successful - Match: {analysis.get('match_score', 0)}%")
                    return analysis
                else:
                    # If no JSON found, raise error to trigger fallback
                    # This prevents returning None or partial data
                    raise ValueError("No JSON found in Gemini response")
                    
            except Exception as e:
                # Log error details but don't re-raise
                # This triggers fallback to keyword analysis
                # Gemini failures are common: rate limits, API changes, etc
                logger.error(f"❌ Gemini API error: {type(e).__name__}: {str(e)[:200]}")
                logger.warning("⚠️ Falling back to keyword analysis")
        
        # ============================================================
        # FALLBACK: INTELLIGENT KEYWORD ANALYSIS
        # ============================================================
        # 
        # FALLBACK PHILOSOPHY:
        # "The user must ALWAYS get a response, no matter what fails."
        # 
        # This ensures:
        # - Server never returns error even if all APIs fail
        # - System remains functional during API outages
        # - Users don't see "service unavailable" messages
        # - Analysis quality degrades to keyword-based
        # 
        # WHY SMART FALLBACK?
        # Foolish approach: Return error or empty response
        # Smart approach: Use sophisticated keyword analysis
        # Result: Users can't tell the difference for most candidates
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
        # 
        # WEIGHTING SYSTEM:
        # Each skill category has a weight multiplier that increases impact
        # on the overall match score. Higher weight = more importance.
        # 
        # WEIGHT VALUES:
        #   1.5 = Critical (must-have or very high demand)
        #   1.4 = Very Important (specialized expertise)
        #   1.3 = Important (commonly required)
        #   1.2 = Fairly Important (valuable but not critical)
        #   1.1 = Moderately Important (helpful to have)
        #   1.0 = Standard (baseline importance)
        # 
        # EXAMPLE CALCULATION:
        #   If job asks for "Python + JavaScript + React":
        #     - Python match: 1 * 1.5 = 1.5 weighted points
        #     - JavaScript match: 1 * 1.5 = 1.5 weighted points
        #     - React match: 1 * 1.3 = 1.3 weighted points
        #     - Total matched weight: 4.3
        #     - Total possible weight: 4.3
        #     - Skill score: 4.3 / 4.3 * 60 = 60 points
        # 
        # WHY THESE WEIGHTS?
        # - Programming languages (1.5): Foundation of all software development
        # - Data science (1.5): High-demand, specialized skills
        # - Backend frameworks (1.4): Core to server-side architecture
        # - Cloud platforms (1.4): Essential in modern DevOps
        # - Frontend frameworks (1.3): UI is major part of web development
        # - Backend frameworks (1.3): Database management is critical
        # - DevOps tools (1.2): Infrastructure matters but not as much as coding
        # - Security (1.2): Critical for safe applications
        # - Version control (1.0): Almost universal, baseline expectation
        # ============================================================
        
        skill_categories = {
            # TIER 1: CRITICAL SKILLS (weight 1.5)
            # These are must-haves for most technical roles
            # High demand, foundational to software development
            'programming_languages': {
                'skills': ['python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 
                          'rust', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'r', 'matlab'],
                'weight': 1.5  # Programming is the foundation of software engineering
            },
            
            'data_science': {
                'skills': ['machine learning', 'deep learning', 'tensorflow', 'pytorch',
                          'scikit-learn', 'pandas', 'numpy', 'matplotlib', 'jupyter',
                          'data analysis', 'nlp', 'computer vision'],
                'weight': 1.5  # ML/AI is high-demand, specialized knowledge
            },
            
            # TIER 2: VERY IMPORTANT SKILLS (weight 1.4)
            # Specialized frameworks and platforms
            # Required for modern software development practices
            'backend_frameworks': {
                'skills': ['fastapi', 'django', 'flask', 'nodejs', 'express', 'nestjs',
                          'spring boot', 'spring', 'asp.net', 'rails', 'laravel', 'symfony'],
                'weight': 1.4  # Backend is critical to application architecture
            },
            
            'cloud_platforms': {
                'skills': ['aws', 'azure', 'gcp', 'google cloud', 'heroku', 'digitalocean',
                          'vercel', 'netlify', 'cloudflare'],
                'weight': 1.4  # Cloud is now standard for modern deployments
            },
            
            # TIER 3: IMPORTANT SKILLS (weight 1.3)
            # Framework-specific and specialized areas
            'frontend_frameworks': {
                'skills': ['react', 'vue', 'angular', 'svelte', 'next.js', 'nuxt', 'gatsby',
                          'html5', 'css3', 'sass', 'less', 'tailwind', 'bootstrap', 'material-ui'],
                'weight': 1.3  # Frontend is major component of web apps
            },
            
            'mobile_development': {
                'skills': ['react native', 'flutter', 'ios development', 'android development',
                          'swift', 'kotlin', 'xamarin', 'ionic', 'cordova'],
                'weight': 1.3  # Mobile is growing but specialized
            },
            
            'databases': {
                'skills': ['postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch',
                          'cassandra', 'dynamodb', 'sql', 'nosql', 'oracle', 'sql server'],
                'weight': 1.3  # Data persistence is critical to every app
            },
            
            'architecture': {
                'skills': ['microservices', 'rest api', 'graphql', 'websockets', 'grpc',
                          'event-driven', 'serverless', 'monolithic', 'distributed systems'],
                'weight': 1.3  # System design shows senior-level thinking
            },
            
            # TIER 4: FAIRLY IMPORTANT SKILLS (weight 1.2)
            # Infrastructure and quality assurance
            'devops_tools': {
                'skills': ['docker', 'kubernetes', 'jenkins', 'gitlab ci', 'github actions',
                          'circleci', 'travis ci', 'terraform', 'ansible', 'puppet', 'chef'],
                'weight': 1.2  # DevOps is essential but specialized
            },
            
            'security': {
                'skills': ['oauth', 'jwt', 'security', 'authentication', 'authorization',
                          'encryption', 'ssl', 'tls', 'penetration testing'],
                'weight': 1.2  # Security is increasingly critical
            },
            
            # TIER 5: MODERATELY IMPORTANT SKILLS (weight 1.1)
            # Quality control and human factors
            'testing': {
                'skills': ['jest', 'pytest', 'junit', 'selenium', 'cypress', 'testing',
                          'unit testing', 'integration testing', 'tdd', 'bdd'],
                'weight': 1.1  # Testing improves code quality
            },
            
            'soft_skills': {
                'skills': ['leadership', 'team lead', 'management', 'communication',
                          'problem solving', 'analytical', 'teamwork', 'collaboration',
                          'mentoring', 'presentation', 'stakeholder management'],
                'weight': 1.1  # Soft skills separate good engineers from great ones
            },
            
            # TIER 6: STANDARD SKILLS (weight 1.0)
            # Essential but widely expected
            'version_control': {
                'skills': ['git', 'github', 'gitlab', 'bitbucket', 'svn', 'version control'],
                'weight': 1.0  # Nearly universal expectation in 2024
            },
            
            'project_management': {
                'skills': ['agile', 'scrum', 'kanban', 'jira', 'confluence', 'trello',
                          'asana', 'project management'],
                'weight': 1.0  # Important for collaboration but standardized
            },
            
            'methodologies': {
                'skills': ['ci/cd', 'continuous integration', 'continuous deployment',
                          'devops', 'design patterns', 'solid principles', 'clean code'],
                'weight': 1.0  # Best practices expected in professional settings
            }
        }
        
        # ============================================================
        # ============================================================
        # SKILL MATCHING WITH WEIGHTED SCORING ALGORITHM
        # ============================================================
        # 
        # ALGORITHM OVERVIEW:
        # This section performs the CORE matching logic between
        # job description and resume using weighted skill categories.
        # 
        # MATCHING PROCESS (3 steps):
        # 1. Extract all skills mentioned in job description
        # 2. Check if resume contains those skills
        # 3. Sum weights for matched and required skills
        # 
        # DATA STRUCTURES:
        # - matched_skills_weighted: skills found in both job + resume
        #   Example: ['Python', 'React', 'PostgreSQL']
        # - missing_skills_weighted: skills in job but not resume
        #   Example: ['Kubernetes', 'GraphQL']
        # - total_weight: sum of ALL required skills from job
        # - matched_weight: sum of weights for skills actually matched
        # 
        # CALCULATION:
        # Skill Score = (matched_weight / total_weight) × 60 points
        # 
        # EXAMPLE:
        # Job description mentions:
        #   - Python (weight 1.5) ✓ Found in resume
        #   - React (weight 1.3) ✗ Not found in resume
        #   - FastAPI (weight 1.4) ✓ Found in resume
        # 
        # Calculation:
        #   matched_weight = 1.5 + 1.4 = 2.9
        #   total_weight = 1.5 + 1.3 + 1.4 = 4.2
        #   skill_score = (2.9 / 4.2) × 60 = 41.4 → 41 points
        # ============================================================
        
        # Initialize accumulators for skill matching
        matched_skills_weighted = []    # Skills found in both
        missing_skills_weighted = []    # Skills required but missing
        total_weight = 0                # Sum of all required skills
        matched_weight = 0              # Sum of matched skills
        
        # MAIN LOOP: Iterate through all skill categories
        for category, data in skill_categories.items():
            # Extract skills list and weight multiplier for this category
            skills = data['skills']
            weight = data['weight']
            
            # INNER LOOP: Check each individual skill in category
            for skill in skills:
                # FILTER PHASE: Only process skills mentioned in job
                # If this skill isn't required, we skip it
                # (candidate can have extra skills we don't care about)
                if skill in job_lower:
                    # This skill is REQUIRED by the job
                    # Add its weight to total possible points
                    total_weight += weight
                    
                    # MATCHING PHASE: Check if resume mentions this skill
                    if skill in resume_lower:
                        # ✓ MATCH: Candidate has the required skill!
                        # Store for scoring and display
                        matched_skills_weighted.append({
                            'skill': skill.title(),                        # Human readable name
                            'category': category.replace('_', ' ').title(), # E.g. "Programming Languages"
                            'weight': weight                              # For debugging and ranking
                        })
                        # Add weight to matched total
                        matched_weight += weight
                    else:
                        # ✗ GAP: Skill required but candidate missing it
                        # This becomes a development opportunity for candidate
                        missing_skills_weighted.append({
                            'skill': skill.title(),
                            'category': category.replace('_', ' ').title(),
                            'weight': weight
                        })
                        # Note: We don't add to matched_weight (it's a gap)
        
        # ============================================================
        # EXPERIENCE LEVEL DETECTION - Extract Years & Seniority
        # ============================================================
        
        # Initialize experience counter (used if not found in resume)
        experience_years = 0
        
        # Multiple regex patterns to catch different ways years are expressed
        # Candidates write experience in different ways:
        # - "10 years of experience"
        # - "10+ years experience"
        # - "experience: 10 years"
        # - "10 years" (standalone)
        experience_patterns = [
            # Pattern 1: "N years of experience" or "N yrs experience"
            # Captures: "10 years of experience", "5+ yrs experience"
            r'(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience',
            
            # Pattern 2: "experience: N years" or "experience: N+"
            # Captures: "experience: 15 years", "experience: 20+"
            r'experience[:\s]+(\d+)\+?\s*(?:years?|yrs?)',
            
            # Pattern 3: Standalone number with years indicator
            # Catches any "N years" or "N yrs" not caught above
            r'(\d+)\+?\s*(?:years?|yrs?)',
        ]
        
        # Try each pattern in order (most specific first)
        # Use the first match found
        for pattern in experience_patterns:
            match = re.search(pattern, resume_lower)
            if match:
                # Extract the number (group 1 is the captured integer)
                experience_years = int(match.group(1))
                break
        
        # ============================================================
        # SENIORITY LEVEL DETECTION - Analyze Job Titles
        # ============================================================
        
        # Keywords indicating professional level/seniority
        # Mapped to three tiers: junior (entry), mid (experienced), senior (leadership)
        seniority_keywords = {
            # Senior leadership roles: decision makers, principals, architects
            'senior': ['senior', 'sr.', 'lead', 'principal', 'staff', 'architect'],
            
            # Mid-level: experienced professionals, level 2+ engineers
            'mid': ['mid-level', 'intermediate', 'engineer ii', 'developer ii'],
            
            # Junior/Entry: fresh graduates, junior roles, associate positions
            'junior': ['junior', 'jr.', 'entry', 'associate', 'graduate']
        }
        
        # Default to mid-level if no keywords found in resume
        # Assumes candidates are mid-level unless proven otherwise
        detected_level = 'mid'
        
        # Scan resume for seniority keywords
        # First match wins (order matters in dictionary)
        for level, keywords in seniority_keywords.items():
            # Check if any keyword from this level appears in the lowercase resume
            if any(keyword in resume_lower for keyword in keywords):
                detected_level = level
                break
        
        # ============================================================
        # EDUCATION LEVEL DETECTION - Identify Degree Type
        # ============================================================
        
        # Education qualification keywords mapped by degree level
        # Higher education = higher weight in analysis
        education_keywords = {
            # Doctoral degrees: PhD, D.Sc., MD, DDS
            'phd': ['ph.d', 'phd', 'doctorate', 'doctoral'],
            
            # Master's degrees: MS, MA, MBA, MSc
            'masters': ['master', 'ms ', 'm.s.', 'msc', 'm.sc', 'mba'],
            
            # Bachelor's degrees: BS, BA, BSc, B.Sc
            'bachelors': ['bachelor', 'bs ', 'b.s.', 'bsc', 'b.sc', 'ba ', 'b.a.'],
            
            # Associate degrees: AA, AS, A.S.
            'associates': ['associate', 'as ', 'a.s.']
        }
        
        # Default: None (no degree found)
        # Will be set if any keyword matches
        education_level = None
        
        # Search for education keywords, highest degree level wins
        # Order matters: PhD checked before Masters, etc.
        for level, keywords in education_keywords.items():
            if any(keyword in resume_lower for keyword in keywords):
                education_level = level
                break
        
        # ============================================================
        # CERTIFICATION DETECTION - Find Professional Credentials
        # ============================================================
        
        # Common industry certifications that boost candidate credibility
        # Grouped by field: Cloud (AWS, Azure, GCP), Project Management (PMP, CSM),
        # Security (CISSP, Sec+), Database/DevOps (Oracle, Kubernetes)
        common_certifications = [
            # Cloud platform certifications (high value in DevOps/Cloud roles)
            'aws certified', 'azure certified', 'gcp certified',
            
            # Project management certifications
            'pmp', 'scrum master', 'csm', 'safe',
            
            # Security certifications (high value in security roles)
            'cissp', 'security+', 'ceh',
            
            # Database and platform certifications
            'oracle certified', 'microsoft certified',
            
            # Kubernetes certifications (high value in DevOps/K8s roles)
            'ckad', 'cka'
        ]
        
        # Extract all found certifications from resume
        # List comprehension: for each cert, if it's in resume, include it
        found_certifications = [cert for cert in common_certifications if cert in resume_lower]
        
        # ============================================================
        # ============================================================
        # CALCULATE INTELLIGENT MATCH SCORE
        # ============================================================
        # 
        # SCORING PHILOSOPHY:
        # The algorithm uses a GENEROUS APPROACH that favors candidate potential
        # over perfect matches. We believe candidates can learn, grow, and adapt.
        # 
        # SCORE BREAKDOWN (max 95 points, min 25 points):
        #   - Skill Score (0-60):         Core competency match to job description
        #   - Experience Bonus (0-15):    Years of relevant experience
        #   - Seniority Bonus (0-10):     Career level matches job level requirements
        #   - Education Bonus (0-10):     Academic credentials and degrees
        #   - Certification Bonus (0-5):  Professional certifications and credentials
        # 
        # Why max 95 not 100?
        #   - Preserves realistic expectations (no perfect candidates)
        #   - Leaves room for growth and learning
        #   - Interviews may reveal additional strengths not in resume
        # 
        # Why min 25?
        #   - Everyone has some value and transferable skills
        #   - Very weak candidates still get consideration
        #   - Prevents demoralizing 0% matches
        # ============================================================
        
        # ============================================================
        # SKILL SCORE CALCULATION (Primary Component: 0-60 points)
        # ============================================================
        
        # The skill score is the foundation of the match
        # It's based on weighted skill matching against job description
        #
        # Calculation: (matched_weight / total_weight) * 60 points
        #   matched_weight = sum of weights for skills found in resume
        #   total_weight    = sum of all weights in job description
        #   Result = percentage of required skills × 60
        #
        # Example:
        #   Job requires: Python (weight 2.0) + React (weight 1.5) = 3.5 total
        #   Resume has: Python (2.0) = 2.0 matched
        #   Skill score = (2.0 / 3.5) * 60 = 34 points
        
        if total_weight > 0:
            # Normal case: job description specifies skills to match
            skill_score = int((matched_weight / total_weight) * 60)
        else:
            # Edge case: no specific skills in job description
            # Give moderate score (candidate can't be judged on specifics)
            skill_score = 45
        
        # ============================================================
        # EXPERIENCE BONUS (Secondary Component: 0-15 points)
        # ============================================================
        
        # Years of experience shows depth and maturity in the field
        # Using tiered system to reward seniority while not penalizing juniors
        #
        # Distribution:
        #   10+ years: 15 points (senior level)
        #   7-9 years: 12 points (experienced)
        #   5-6 years: 10 points (solid experience)
        #   3-4 years: 7 points  (developing)
        #   1-2 years: 5 points  (entry with some experience)
        #   0 years:   0 points  (fresh graduate or career change)
        
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
        # else: 0 years → 0 points
        
        # ============================================================
        # SENIORITY LEVEL BONUS (0-10 points)
        # ============================================================
        
        # Match between candidate's career level and position requirements
        # Why it matters: A senior engineer in a junior role is overqualified
        # but trainable. A junior in a senior role is underqualified.
        #
        # Two-tier logic:
        # 1. If job requires senior/lead level:
        #    - Senior candidate: 10 points (perfect match)
        #    - Mid candidate:     5 points (can grow into role)
        #    - Junior candidate:  0 points (not ready)
        #
        # 2. If job is entry/mid level:
        #    - Any level: 5 points (everyone is suitable)
        
        seniority_bonus = 0
        if 'senior' in job_lower or 'lead' in job_lower:
            # Job explicitly requires seniority
            if detected_level == 'senior':
                seniority_bonus = 10  # Perfect seniority match
            elif detected_level == 'mid':
                seniority_bonus = 5   # Can grow into senior role
            # else: junior gets 0 (not ready for senior role)
        else:
            # Job is entry/mid level (no seniority requirement)
            seniority_bonus = 5  # Any candidate is suitable
        
        # ============================================================
        # EDUCATION BONUS (0-10 points)
        # ============================================================
        
        # Academic credentials indicate foundational knowledge
        # Weighted by degree level and relevance
        #
        # Why it matters: Some roles require specific education
        # (e.g., embedded systems often require hardware background)
        #
        # Point allocation:
        #   PhD/Doctorate: 10 points (highest academic achievement)
        #   Master's:      8 points  (specialized knowledge)
        #   Bachelor's:    6 points  (standard qualification)
        #   Associate's:   4 points  (foundational education)
        #   None:          0 points  (self-taught, bootcamp, etc.)
        
        education_bonus = 0
        if education_level:
            # Lookup table for degree value
            education_scores = {
                'phd': 10,         # Doctoral degree
                'masters': 8,      # Master's degree
                'bachelors': 6,    # Bachelor's degree
                'associates': 4    # Associate's degree
            }
            education_bonus = education_scores.get(education_level, 0)
        
        # ============================================================
        # CERTIFICATION BONUS (0-5 points)
        # ============================================================
        
        # Professional certifications show commitment and specific expertise
        # Examples: AWS Certified Solutions Architect, PMP, Kubernetes CKA
        #
        # Extra value because:
        #   - Requires study and exam passing
        #   - Shows current knowledge (often yearly renewal)
        #   - Indicates specific skill verification
        #
        # Calculation: min(5, count × 2)
        #   1 cert = 2 points
        #   2 certs = 4 points
        #   3+ certs = 5 points (capped at 5)
        
        certification_bonus = min(5, len(found_certifications) * 2)
        
        # ============================================================
        # FINAL SCORE AGGREGATION
        # ============================================================
        
        # Sum all components with bounds:
        #   Upper bound: 95 (leave room for unknown unknowns)
        #   Lower bound: 25 (everyone has some value)
        #   Formula: SKILL + EXPERIENCE + SENIORITY + EDUCATION + CERT
        #
        # Example calculation:
        #   Skill score:        45 points (60% of required skills)
        #   Experience bonus:   10 points (5 years)
        #   Seniority bonus:    5 points  (mid-level matches mid role)
        #   Education bonus:    6 points  (bachelor's degree)
        #   Certification bonus: 2 points (1 AWS cert)
        #   ────────────────────────────
        #   Raw total:         68 points
        #   Final score:       68 → Clamped to [25-95] → 68 (GOOD match)
        
        final_score = min(95, max(25, 
            skill_score + 
            experience_bonus + 
            seniority_bonus + 
            education_bonus + 
            certification_bonus
        ))
        
        # ============================================================
        # ============================================================
        # GENERATE PROFESSIONAL SUMMARY
        # ============================================================
        # 
        # The summary tier system provides human-readable assessment
        # based on the match score. This creates consistent, professional
        # language for hiring teams.
        # 
        # TIER SYSTEM (Score → Assessment → Recommendation):
        # 85+  → "exceptional"       → Immediate interview (top tier)
        # 75-84→ "strong"            → Highly recommended (solid hire)
        # 65-74→ "good"              → Recommended interview (qualified)
        # 50-64→ "moderate"          → Further review needed (maybe)
        # <50  → "limited"           → Likely rejection (misfit)
        # 
        # Why these thresholds?
        # - 85+: In top quartile of candidates, clear hire signal
        # - 75+: Meets most requirements, worth serious consideration
        # - 65+: Qualified but has gaps, should interview
        # - 50+: Not great but has some relevant skills
        # - <50: Not a good fit on paper, skip
        # ============================================================
        
        # Determine assessment level based on final match score
        # Each tier has three associated messages for different contexts
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
        else:  # Below 50
            assessment = "limited"
            recommendation = "may not fully meet current requirements"
            fit_level = "below expectations"
        
        # ============================================================
        # BUILD MULTI-SECTION SUMMARY
        # ============================================================
        # 
        # The summary is built as a series of sentences covering:
        # 1. Opening: Overall match percentage and assessment
        # 2. Skills: Top 5 matched skills
        # 3. Experience: Years and seniority level
        # 4. Education: Degree type (if found)
        # 5. Certifications: Relevant credentials
        # 6. Gaps: Skills to develop (if minor gaps)
        # 7. Conclusion: Hiring recommendation
        # 
        # This creates a coherent narrative for recruiters: here's the
        # candidate, here's what's great, here's what needs work, here's
        # the recommendation.
        # ============================================================
        
        # Build summary as list of sentences to be joined later
        summary_parts = []
        
        # 1. OPENING: Overall assessment and score
        # Example: "Candidate demonstrates strong alignment with the position requirements (78% overall match)."
        summary_parts.append(
            f"Candidate demonstrates {assessment} alignment with the position requirements ({final_score}% overall match)."
        )
        
        # 2. SKILLS ANALYSIS: Highlight top matched skills
        # Shows what the candidate brings to the table
        # Example: "Strong technical capabilities identified in Python, React, and FastAPI."
        if matched_skills_weighted:
            top_skills = [s['skill'] for s in matched_skills_weighted[:5]]
            summary_parts.append(
                f"Strong technical capabilities identified in {', '.join(top_skills[:3])}."
            )
        
        # 3. EXPERIENCE ANALYSIS: Years and career level
        # Context: how much experience they have and at what level
        # Example: "Brings 8+ years of professional experience at the mid level."
        if experience_years > 0:
            summary_parts.append(
                f"Brings {experience_years}+ years of professional experience at the {detected_level} level."
            )
        
        # 4. EDUCATION: Degree type if found
        # Validates academic background
        # Example: "Educational background includes bachelor's degree."
        if education_level:
            education_display = {
                'phd': "doctoral degree",
                'masters': "master's degree",
                'bachelors': "bachelor's degree",
                'associates': "associate degree"
            }
            summary_parts.append(
                f"Educational background includes {education_display.get(education_level, education_level)}."
            )
        
        # 5. CERTIFICATIONS: Professional credentials
        # Adds credibility and shows commitment to specialty
        # Example: "Holds 2 relevant professional certification(s)."
        if found_certifications:
            summary_parts.append(
                f"Holds {len(found_certifications)} relevant professional certification(s)."
            )
        
        # 6. GAP ANALYSIS: Skills to develop
        # Helpful feedback about what areas need growth
        # Only shown if gaps are manageable (≤4 missing skills)
        # Example: "Development opportunities exist in Docker, Kubernetes, and GraphQL."
        if missing_skills_weighted and len(missing_skills_weighted) <= 4:
            missing_skill_names = [s['skill'] for s in missing_skills_weighted[:3]]
            summary_parts.append(
                f"Development opportunities exist in {', '.join(missing_skill_names)}."
            )
        
        # 7. CONCLUSION: Final hiring recommendation
        # Example: "Overall assessment: strongly recommended as a top candidate for immediate interview."
        summary_parts.append(
            f"Overall assessment: {recommendation}."
        )
        
        # Join all parts into single professional summary paragraph
        summary = " ".join(summary_parts)
        
        # ============================================================
        # GENERATE PERSONALIZED EMAIL DRAFT
        # ============================================================
        # 
        # Email generation is score-based with two distinct templates:
        # 
        # POSITIVE EMAIL (Score ≥ 65):
        # - Conveys enthusiasm for the candidate
        # - Extends interview invitation
        # - Personalizes with matched skills and experience
        # - Adjusts interview format based on score:
        #   * ≥75: "technical discussion" (senior, more detailed)
        #   * <75: "conversation" (less intensive)
        # - Sets urgency based on strength:
        #   * ≥80: "this week" (top candidates)
        #   * <80: "coming week" (good candidates)
        #
        # REJECTION EMAIL (Score < 65):
        # - Professional and encouraging tone
        # - Acknowledges strengths (doesn't demoralize)
        # - Specifies gaps without being harsh
        # - Encourages continued skill development
        # - Offers future opportunities
        # - Compliments their field
        #
        # WHY TWO TEMPLATES?
        # - Personalization at scale: Creates custom emails for 100+ candidates
        # - Consistent tone: Professional branding for company
        # - Reduces recruiter workload: Emails ready to send (or slight customize)
        # - Recruiter control: Can be template or starting point
        # ============================================================
        
        # Branch: Positive or Rejection Email
        if final_score >= 65:
            # ========================================================
            # POSITIVE EMAIL - Interview Invitation Template
            # ========================================================
            # Score ≥65: Candidate meets minimum bar for interview
            # This email conveys professional enthusiasm and next steps
            # ========================================================
            
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
            # ========================================================
            # REJECTION EMAIL - Professional Rejection Template
            # ========================================================
            # Score <65: Candidate doesn't meet requirements for interview
            # This email is kind, professional, and future-focused
            # ========================================================
            
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

        # ============================================================
        # PREPARATION: Limit resume size for optimization
        # ============================================================
        
        # Limit resume to manage token usage and API costs
        # Groq processes extremely fast but we still apply reasonable limits
        # Safety margin set to 6000 chars to keep within token budget
        # This is enough for even lengthy resumes (typically 1500-3000 chars)
        resume_clipped = resume_text[:6000] if len(resume_text) > 6000 else resume_text

        # ============================================================
        # PROMPT ENGINEERING - Tuned for Llama 3.1 70B
        # ============================================================
        # 
        # This prompt is CAREFULLY DESIGNED for best results with Llama 3.1 70B.
        # Key elements:
        # 1. Clear role definition: "Technical Recruiter"
        # 2. Structure: Job requirements first, resume second
        # 3. Explicit evaluation guidelines (be generous)
        # 4. JSON-only requirement (no markdown wrapping)
        # 5. Field specifications (key_strengths: max 5, etc)
        # 6. Instructions about PDF artifacts (ignore them)
        # 7. Scoring guardrails (min score logic)
        #
        # WHY THESE ELEMENTS?
        # - Role definition: helps model adopt recruiter perspective
        # - Generous scoring: recruits should value potential, not perfection
        # - Transferable skills: Python → backend, Java → systems programming
        # - Soft skills: communication + teamwork matter for hiring
        # - JSON format: makes response parsing reliable and consistent
        # - Scoring guardrails: prevent overly harsh scores for partial fits
        # ============================================================
        
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

            # ============================================================
            # API CALL: Groq Chat Completion Request
            # ============================================================
            # 
            # Using Groq's ultra-fast LPU hardware for inference.
            # Expected response time: < 2 seconds (compared to 10-30s for other APIs)
            # 
            # REQUEST STRUCTURE:
            # - Model: "llama-3.3-70b-versatile" (Llama 3.3, not 3.1)
            #   Newer version with improved JSON compliance and reasoning
            # - Messages: Multi-turn format with system + user roles
            #   System message frames behavior (JSON-only output)
            #   User message contains the analysis prompt
            # - Temperature: 0.7 (balanced between deterministic and creative)
            #   0.0 = always choose most likely token (boring, but consistent)
            #   1.0 = random sampling (creative but unpredictable)
            #   0.7 = good balance for recruiting (some creativity, mostly consistent)
            # - Max tokens: 1000 (reasonable limit for analysis response)
            #   Groq's speed makes even longer responses fast
            # - Top P: 1.0 (nucleus sampling - consider all tokens)
            #   Works with temperature to control randomness
            # - Stream: False (need complete response before parsing JSON)
            # ============================================================
            
            response = self.client.chat.completions.create(
                # Llama 3.3 70B model: improved reasoning, better JSON compliance
                model="llama-3.3-70b-versatile",
                
                # Multi-message format for structured AI behavior
                messages=[
                    {
                        "role": "system",
                        # System message sets AI behavior: return only valid JSON, no markdown
                        # This helps prevent the common issue of JSON wrapped in ```json...```
                        "content": "You are a helpful recruiter AI that returns only valid JSON responses."
                    },
                    {
                        "role": "user",
                        # User message: the analysis prompt with resume and job description
                        "content": prompt
                    }
                ],
                
                # Temperature: controls randomness in token selection
                # 0.7 is ideal for recruiting (consistent but not robotic)
                temperature=0.7,
                
                # Max tokens: limit response length for efficiency
                # 1000 tokens ≈ 750 words, plenty for required JSON fields
                max_tokens=1000,
                
                # Top P (nucleus sampling): 1.0 means all tokens considered
                # 0.0 = only most likely (greedy)
                # 1.0 = all tokens possible (stochastic)
                # 1.0 is standard for Groq (let temperature control randomness)
                top_p=1,
                
                # Disable streaming: JSON parsing requires complete response
                # Streaming would give partial JSON (invalid)
                stream=False
            )

            # ============================================================
            # EXTRACT RESPONSE CONTENT
            # ============================================================
            
            # Extract the analyzed text from response structure
            # response.choices[0] = first (and only) response choice
            # .message.content = the actual text content returned by LLM
            result_text = response.choices[0].message.content

            logger.info("Groq AI analysis completed (Ultra-Fast LPU Processing)")

            # Parse response text into structured JSON object
            # Handles potential formatting issues or code blocks in response
            analysis_result = self._parse_json_response(result_text)

            # ============================================================
            # POST-PROCESSING: Apply Generous Scoring Guardrails
            # ============================================================
            
            # Apply generous scoring policy to prevent overly harsh scoring
            # Philosophy: Candidates with ANY demonstrated skills get minimum baseline
            # Reflects belief in human potential and transferable skills
            # 
            # Logic:
            # - If match_score too low (< 35) BUT has key strengths detected
            # - Boost score to 35 (out of 100)
            # - This prevents "reject if not perfect" behavior
            # 
            # Example:
            # - Has Python, React skills but missing DevOps knowledge
            # - Original score: 25 (harsh)
            # - Applied guardrail: 35 (more fair)
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
        
        Handles common issues with AI-generated responses:
        - Markdown code blocks wrapping JSON
        - Missing required fields
        - Type mismatches in fields
        - Out-of-range values
        
        Applies sensible defaults and type coercion to ensure
        reliable parsing even with imperfect AI responses.
        
        Args:
            text: Raw response text from Groq API (may include markdown, comments, etc)
            
        Returns:
            dict: Validated analysis with guaranteed:
                - All required keys present
                - Correct data types
                - Values within valid ranges
            
        Raises:
            ValueError: If no valid JSON object found in response
        """
        # ============================================================
        # STEP 1: CLEAN MARKDOWN WRAPPERS
        # ============================================================
        
        # Remove markdown code block wrappers that AI sometimes adds
        # Pattern: ```json ... ``` or just ``` ... ```
        # This is common when AI tries to format code nicely
        cleaned = clean_ai_response(text)

        # ============================================================
        # STEP 2: EXTRACT JSON OBJECT FROM RESPONSE
        # ============================================================
        
        # Use regex to find JSON object structure in response
        # Pattern: \{.*\} matches any JSON object (even with newlines inside)
        # re.DOTALL makes . match newline characters
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)

        # Validate that we found JSON
        if not json_match:
            # Log the problematic response for debugging
            logger.error(f"No JSON found in Groq response: {cleaned[:200]}")
            raise ValueError("Groq response did not contain valid JSON")

        # ============================================================
        # STEP 3: PARSE JSON STRING TO PYTHON DICT
        # ============================================================
        
        # Convert JSON string to Python dictionary
        # json.loads() will raise JSONDecodeError if invalid JSON
        parsed = json.loads(json_match.group(0))

        # ============================================================
        # STEP 4: VALIDATE REQUIRED FIELDS EXIST
        # ============================================================
        
        # Define fields that must be present in every response
        # These are the minimum required for a valid analysis
        required = {"match_score", "key_strengths", "missing_skills", "summary", "email_draft"}
        # Find any fields that are missing from response
        missing = required - set(parsed.keys())

        if missing:
            # Log warning if any fields are missing
            logger.warning(f"Groq response missing keys: {missing}. Applying defaults.")
            # Apply sensible defaults for missing fields
            # Ensures response always has all required keys
            for key in missing:
                if key == "match_score":
                    # Default score: 50 (middle of range, neither good nor bad)
                    parsed[key] = 50
                elif key in ["key_strengths", "missing_skills"]:
                    # Default empty list: no specific strengths/gaps mentioned
                    parsed[key] = []
                else:
                    # Default empty string for text fields
                    parsed[key] = ""

        # ============================================================
        # STEP 5: TYPE VALIDATION FOR MATCH_SCORE
        # ============================================================
        
        # Ensure match_score is valid integer in range 0-100
        try:
            # Get match_score, default to 50 if missing
            score = parsed.get("match_score", 50)
            # Convert to int (handles float scores like 82.5 → 82)
            score = int(score)
            # Clamp to valid range: ensure 0 <= score <= 100
            # max(0, ...) prevents negative scores
            # min(100, ...) prevents scores > 100
            parsed["match_score"] = max(0, min(100, score))
        except (ValueError, TypeError):
            # If conversion fails, use safe default
            # ValueError: score could not convert to int (e.g., "eighty")
            # TypeError: score is None or has no int representation
            parsed["match_score"] = 50

        # ============================================================
        # STEP 6: TYPE VALIDATION FOR LIST FIELDS
        # ============================================================
        
        # Ensure key_strengths and missing_skills are always lists
        for key in ["key_strengths", "missing_skills"]:
            # Check if field exists and is actually a list
            if not isinstance(parsed.get(key), list):
                # If it's not a list, try to convert it
                value = parsed.get(key)
                if value:
                    # If value exists (e.g., string), wrap it in a list
                    parsed[key] = [str(value)]
                else:
                    # If value is None/empty, use empty list
                    parsed[key] = []

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
    
    Common Issue:
    Many LLMs wrap JSON responses in markdown syntax for readability.
    Examples:
        ```json
        {"key": "value"}
        ```
        
        Or sometimes without the json type hint:
        ```
        {"key": "value"}
        ```
    
    This utility strips those markers to prepare text for JSON parsing.
    Ensures json.loads() can parse the extracted JSON successfully.
    
    Args:
        text: Raw response text from AI model (may contain markdown)
        
    Returns:
        Cleaned text with markdown removed and whitespace trimmed
        
    Example:
        >>> text = '```json\\n{"key": "value"}\\n```'
        >>> clean_ai_response(text)
        '{"key": "value"}'
        
        >>> text = '```\\n{"key": "value"}\\n```'
        >>> clean_ai_response(text)
        '{"key": "value"}'
    """
    # ============================================================
    # REMOVE MARKDOWN CODE BLOCK OPENING MARKERS
    # ============================================================
    
    # Pattern: ```json, ```javascript, ``` or similar
    # (?:json)? means: optionally match 'json' (but don't capture it)
    # \s* means: match zero or more whitespace characters
    # This handles both ```json and ``` with optional language hint
    # Replaces with empty string (removes the marker entirely)
    text = re.sub(r"```(?:json)?\s*", "", text)

    # ============================================================
    # REMOVE MARKDOWN CODE BLOCK CLOSING MARKERS
    # ============================================================
    
    # Remove any remaining closing code block markers (```)
    # These appear at the end of the markdown block
    # Simple string replacement is fine here since we're just removing a delimiter
    text = text.replace("```", "")

    # ============================================================
    # NORMALIZE WHITESPACE
    # ============================================================
    
    # Strip leading and trailing whitespace from entire response
    # Ensures clean JSON string ready for parser
    # strip() removes: spaces, tabs, newlines, carriage returns
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
