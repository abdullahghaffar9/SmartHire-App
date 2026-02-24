/**
 * SmartHire Frontend Application
 * ==============================
 *
 * A modern, responsive React application for AI-powered resume analysis.
 * Provides an intuitive interface for uploading resumes and evaluating
 * candidate fit against job descriptions.
 *
 * Data Flow:
 *   1. Recruiter uploads a PDF resume via drag-and-drop or file picker.
 *   2. Recruiter enters the job description in the text area.
 *   3. On submit, the PDF and job description are sent to the FastAPI backend.
 *   4. The backend runs 3-tier AI analysis and returns a structured JSON result.
 *   5. The UI renders the match score, strengths, gaps, summary, and email draft.
 *
 * Features:
 *   - Drag-and-drop PDF resume upload with visual feedback
 *   - Real-time job description input
 *   - AI-powered resume analysis with 3-tier fallback (Groq → Gemini → Keywords)
 *   - Animated results display with detailed scoring
 *   - Email draft generation for candidate communication
 *   - Copy-to-clipboard functionality for the generated email
 *   - Responsive design (mobile, tablet, desktop)
 *   - Smooth animations and transitions via Framer Motion
 *
 * Technology Stack:
 *   - React 18        - UI framework with hooks
 *   - Vite 5+         - Build tool and HMR dev server
 *   - TailwindCSS 3   - Utility-first CSS framework
 *   - Framer Motion   - Declarative animation library
 *   - Axios           - Promise-based HTTP client
 *   - Lucide React    - Lightweight SVG icon library
 *
 * Environment Configuration:
 *   VITE_API_URL - Backend API endpoint (default: http://127.0.0.1:8000)
 *                  Set to the deployed Railway/Render URL in production.
 *
 * Author: Abdullah Ghaffar
 * Repository: https://github.com/abdullahghaffar9/SmartHire-App
 * License: MIT
 * Version: 1.0.0
 */

import React, { useState, useRef } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, Copy, CheckCircle, AlertCircle, Zap, FileText, TrendingUp } from 'lucide-react';

/**
 * API Configuration
 * Production-ready: Uses environment variable with sensible fallback
 * Allows different backend URLs in development vs production
 */
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

/**
 * AnimatedCounter Component
 *
 * Displays an animated number counter that increments from 0 to a target value.
 * Used for showing match score percentages with smooth animation.
 *
 * Props:
 *   value (number) - Target value to animate to
 *   duration (number) - Animation duration in seconds (default: 2)
 *
 * Example:
 *   <AnimatedCounter value={85} duration={2} />
 *   // Animates from 0 to 85 over 2 seconds
 */
const AnimatedCounter = ({ value, duration = 2 }) => {
  const [count, setCount] = React.useState(0);

  /**
   * useEffect Hook for Animation Loop
   * - Uses requestAnimationFrame for smooth 60fps animation
   * - Calculates progress based on elapsed time
   * - Cleans up animation frame on unmount
   */
  React.useEffect(() => {
    let startTime;
    let animationId;

    const animate = (currentTime) => {
      if (!startTime) startTime = currentTime;
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / (duration * 1000), 1);
      setCount(Math.floor(progress * value));

      if (progress < 1) {
        animationId = requestAnimationFrame(animate);
      }
    };

    animationId = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animationId);
  }, [value, duration]);

  return <span>{count}</span>;
};

/**
 * SmartHire Main Application Component
 *
 * Core component managing the entire resume analysis workflow.
 * Handles file upload, API communication, and results display.
 */
export default function App() {
  // ============================================================
  // STATE MANAGEMENT
  // ============================================================
  
  /**
   * Component State Variables
   * - resumeFile: Current selected resume file
   * - jobDescription: Job requirements text input
   * - loading: API request in-progress flag
   * - error: Error message for display
   * - analysisResult: Parsed AI analysis response
   * - copied: Clipboard copy confirmation state
   */
  const [resumeFile, setResumeFile] = useState(null);
  const [jobDescription, setJobDescription] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [copied, setCopied] = useState(false);
  
  // Reference to hidden file input for programmatic access
  const fileInputRef = useRef(null);
  
  // Reference to drop zone for drag-and-drop detection
  const dropZoneRef = useRef(null);

  // ============================================================
  // FILE HANDLING FUNCTIONS
  // ============================================================
  
  /**
   * Handle file selection from file input
   * Validates file type and updates resume state
   * Only accepts PDF files
   */
  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setResumeFile(file);
      setError(null);
    } else {
      setError('Please select a valid PDF file');
      setResumeFile(null);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZoneRef.current?.classList.add('border-blue-500', 'bg-blue-50');
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZoneRef.current?.classList.remove('border-blue-500', 'bg-blue-50');
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    dropZoneRef.current?.classList.remove('border-blue-500', 'bg-blue-50');

    const file = e.dataTransfer.files?.[0];
    if (file && file.type === 'application/pdf') {
      setResumeFile(file);
      setError(null);
    } else {
      setError('Please drop a valid PDF file');
      setResumeFile(null);
    }
  };

  // ============================================================
  // API COMMUNICATION & ANALYSIS
  // ============================================================
  
  /**
   * Submit resume and job description for AI analysis
   * Sends multipart form data to backend
   * Handles loading states and error reporting
   */
  const analyzeCandidate = async () => {
    if (!resumeFile || !jobDescription.trim()) {
      setError('Please upload a resume and enter a job description');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', resumeFile);
      formData.append('job_description', jobDescription);

      // Send to backend API with proper content-type for file upload
      const response = await axios.post(
        `${API_URL}/analyze-resume`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );

      setAnalysisResult(response.data.ai_analysis);
      setError(null);
    } catch (err) {
      console.error('Error:', err);
      setError(
        err.response?.data?.detail ||
        'Failed to analyze resume. Please try again.'
      );
      setAnalysisResult(null);
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // UTILITY FUNCTIONS
  // ============================================================
  
  /**
   * Copy email draft to clipboard
   * Shows confirmation message for 2 seconds
   */
  const copyToClipboard = () => {
    if (analysisResult?.email_draft) {
      navigator.clipboard.writeText(analysisResult.email_draft);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const getMatchScoreColor = (score) => {
    if (score >= 75) return 'text-green-500';
    if (score >= 50) return 'text-yellow-500';
    return 'text-red-500';
  };

  const getMatchScoreBgColor = (score) => {
    if (score >= 75) return 'bg-green-500/10';
    if (score >= 50) return 'bg-yellow-500/10';
    return 'bg-red-500/10';
  };

  const getMatchScoreBorderColor = (score) => {
    if (score >= 75) return 'border-green-500';
    if (score >= 50) return 'border-yellow-500';
    return 'border-red-500';
  };

  // ============================================================
  // RENDER
  // ============================================================
  return (
    <div className="min-h-screen relative overflow-hidden text-slate-100 font-sans">
      {/* Animated Mesh Gradient Background */}
      <div className="fixed inset-0 -z-10">
        {/* Base gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950"></div>
        
        {/* Animated mesh gradients */}
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-blue-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-70 animate-blob"></div>
        <div className="absolute top-0 right-1/4 w-96 h-96 bg-purple-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-70 animate-blob" style={{animationDelay: '2s'}}></div>
        <div className="absolute bottom-0 left-1/3 w-96 h-96 bg-cyan-500/30 rounded-full mix-blend-multiply filter blur-3xl opacity-70 animate-blob" style={{animationDelay: '4s'}}></div>
        
        {/* Grid overlay for depth */}
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wMiI+PHBhdGggZD0iTTM2IDM0djItSDI0di0yaDEyek0zNiAyOHYySDI0di0yaDEyek0zNiAyMnYySDI0di0yaDEyeiIvPjwvZz48L2c+PC9zdmc+')] opacity-20"></div>
      </div>

      {/* Header - Premium Branding */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="relative z-10 backdrop-blur-xl bg-slate-900/95 border-b border-slate-800 sticky top-0"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex items-center justify-between gap-4">
            {/* Logo & Title */}
            <div className="flex items-center gap-3 min-w-0">
              <motion.div
                whileHover={{ scale: 1.15, rotate: 10 }}
                whileTap={{ scale: 0.95 }}
                className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/30"
              >
                <Zap className="w-7 h-7 text-white" />
              </motion.div>
              <div className="min-w-0">
                <h1 className="text-2xl sm:text-3xl font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
                  SmartHire
                </h1>
                <p className="text-xs sm:text-sm text-slate-400 truncate">AI-Powered Candidate Intelligence</p>
              </div>
            </div>

            {/* Right side badges */}
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap justify-end">
              {/* AI Powered Badge */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 }}
                className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-purple-500/10 border border-purple-500/30 rounded-lg hover:bg-purple-500/20 transition-colors"
              >
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></div>
                  <span className="text-xs font-semibold text-purple-300">Groq AI - Ultra-Fast</span>
                </div>
              </motion.div>

              {/* Premium Badge */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="flex items-center gap-2 px-4 py-1.5 bg-gradient-to-r from-emerald-500/10 to-green-500/10 border border-emerald-500/40 rounded-lg hover:border-emerald-500/60 transition-colors"
              >
                <svg className="w-4 h-4 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                <span className="text-xs sm:text-sm font-semibold text-emerald-300">Premium</span>
              </motion.div>
            </div>
          </div>
        </div>
      </motion.div>

      {/* How It Works Section */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.3 }}
        className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12"
      >
        <div className="text-center mb-12">
          <h2 className="text-3xl sm:text-4xl font-bold text-white mb-3">How It Works</h2>
          <p className="text-slate-400 max-w-2xl mx-auto">
            Our advanced AI system analyzes resumes with 3-tier intelligence for 100% reliability
          </p>
        </div>

        {/* Steps Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Step 1 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-xl p-6 hover:bg-white/10 hover:border-white/20 transition-all duration-300"
          >
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400 mb-4">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">1. Upload Resume</h3>
            <p className="text-sm text-slate-400">
              Submit a PDF resume and paste the job description for evaluation
            </p>
          </motion.div>

          {/* Step 2 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-xl p-6 hover:bg-white/10 hover:border-white/20 transition-all duration-300"
          >
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-gradient-to-br from-purple-500 to-pink-400 mb-4">
              <svg className="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M13 7H7v6h6V7z" />
                <path fillRule="evenodd" d="M7 2a1 1 0 012 0v1h2V2a1 1 0 112 0v1h2a2 2 0 012 2v2h1a1 1 0 110 2h-1v2h1a1 1 0 110 2h-1v2a2 2 0 01-2 2h-2v1a1 1 0 11-2 0v-1H9v1a1 1 0 11-2 0v-1H5a2 2 0 01-2-2v-2H2a1 1 0 110-2h1V9H2a1 1 0 010-2h1V5a2 2 0 012-2h2V2zM5 5h10v10H5V5z" clipRule="evenodd" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">2. AI Analysis</h3>
            <p className="text-sm text-slate-400">
              Groq AI evaluates fit in ~1 second using advanced LPU technology
            </p>
          </motion.div>

          {/* Step 3 */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 }}
            className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-xl p-6 hover:bg-white/10 hover:border-white/20 transition-all duration-300"
          >
            <div className="flex items-center justify-center w-12 h-12 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-400 mb-4">
              <TrendingUp className="w-6 h-6 text-white" />
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">3. Get Insights</h3>
            <p className="text-sm text-slate-400">
              View match score, strengths, gaps, and ready-to-send email responses
            </p>
          </motion.div>
        </div>

        {/* Features Grid */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7 }}
          className="mt-12 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
        >
          {[
            { label: 'Ultra-Fast Processing', desc: '~1s analysis' },
            { label: 'Smart AI System', desc: 'Groq + Fallback' },
            { label: 'Accurate Scoring', desc: 'Generous evaluation' },
            { label: 'Private Analysis', desc: 'Secure processing' }
          ].map((feature, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8 + i * 0.1 }}
              className="flex items-center gap-3 p-4 rounded-lg bg-white/5 border border-white/10"
            >
              <div className="flex-1">
                <p className="font-semibold text-white text-sm">{feature.label}</p>
                <p className="text-xs text-slate-400">{feature.desc}</p>
              </div>
            </motion.div>
          ))}
        </motion.div>
      </motion.div>

      {/* Main Content */}
      <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 sm:gap-8">
          {/* ============================================================ */}
          {/* LEFT SIDE: INPUTS */}
          {/* ============================================================ */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="space-y-6"
          >
            <div>
              <h2 className="text-2xl sm:text-3xl font-bold mb-2">Upload & Analyze</h2>
              <p className="text-sm text-slate-400">Evaluate candidate fit in seconds</p>
            </div>

            {/* Resume Upload Drop Zone */}
            <motion.div
              ref={dropZoneRef}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="relative group cursor-pointer animate-float"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-blue-600 to-cyan-600 rounded-2xl opacity-0 group-hover:opacity-20 blur-xl transition-all duration-300"></div>
              <div className="relative glass-card-strong rounded-2xl p-8 sm:p-10 transition-all duration-300 shadow-2xl hover:shadow-blue-500/20 border-2 border-dashed border-white/30 group-hover:border-white/50">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handleFileChange}
                  className="hidden"
                />

                <AnimatePresence mode="wait">
                  {!resumeFile ? (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -10 }}
                      className="flex flex-col items-center justify-center text-center"
                    >
                      <motion.div
                        animate={{ y: [0, -8, 0] }}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <FileText className="w-12 sm:w-16 h-12 sm:h-16 text-blue-400 mb-4 mx-auto opacity-80" />
                      </motion.div>
                      <h3 className="text-lg sm:text-xl font-semibold mb-2">Drop your resume here</h3>
                      <p className="text-slate-400 text-sm mb-4">
                        or click to browse your files
                      </p>
                      <p className="text-xs text-slate-500">PDF format, max 10MB</p>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="filled"
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      exit={{ opacity: 0, scale: 0.9 }}
                      className="flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-green-500/20 border border-green-500/40">
                          <FileText className="w-6 h-6 text-green-400" />
                        </div>
                        <div className="text-left">
                          <p className="font-semibold text-sm truncate">{resumeFile.name}</p>
                          <p className="text-xs text-slate-500">
                            {(resumeFile.size / 1024).toFixed(0)} KB
                          </p>
                        </div>
                      </div>
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="p-2 rounded-full bg-green-500/20"
                      >
                        <CheckCircle className="w-6 h-6 text-green-400" />
                      </motion.div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>

            {/* Job Description */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
              className="animate-float"
              style={{animationDelay: '1s'}}
            >
              <div className="glass-card-strong rounded-2xl p-6 sm:p-7 shadow-2xl hover:shadow-purple-500/10 transition-all duration-300">
                <label className="block text-sm font-semibold text-white mb-3">
                  Job Description
                </label>
                <textarea
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  placeholder="Paste the job description, requirements, and desired qualifications..."
                  className="w-full h-40 px-4 py-3 rounded-lg bg-white/5 border border-white/20 text-white placeholder-slate-500 focus:outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-500/30 transition-all resize-none backdrop-blur-sm"
                />
              </div>
              <p className="text-xs text-slate-500 mt-2">
                {jobDescription.length} characters
              </p>
            </motion.div>

            {/* Error Message */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="flex gap-3 p-4 bg-red-500/10 backdrop-blur-xl border border-red-500/30 rounded-xl"
                >
                  <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                  <p className="text-red-400 text-sm">{error}</p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Analyze Button */}
            <motion.button
              onClick={analyzeCandidate}
              disabled={loading || !resumeFile || !jobDescription.trim()}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className={`w-full py-4 rounded-xl font-semibold text-white transition-all duration-200 flex items-center justify-center gap-2 shadow-lg ${
                loading || !resumeFile || !jobDescription.trim()
                  ? 'bg-slate-700/50 cursor-not-allowed opacity-50 backdrop-blur-xl'
                  : 'bg-gradient-to-r from-blue-600 to-cyan-600 hover:shadow-2xl hover:shadow-blue-500/20 backdrop-blur-xl'
              }`}
            >
              {loading ? (
                <>
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
                  >
                    <Zap className="w-5 h-5" />
                  </motion.div>
                  <span>Analyzing...</span>
                </>
              ) : (
                <>
                  <Zap className="w-5 h-5" />
                  <span>Analyze Candidate</span>
                </>
              )}
            </motion.button>

            {/* Loading Message */}
            <AnimatePresence>
              {loading && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="p-4 bg-blue-500/10 backdrop-blur-xl border border-blue-500/30 rounded-xl"
                >
                  <p className="text-blue-300 text-sm flex items-center gap-2">
                    <motion.span
                      animate={{ opacity: [0.3, 1, 0.3] }}
                      transition={{ duration: 1.5, repeat: Infinity }}
                    >
                      ●
                    </motion.span>
                    AI is evaluating the candidate match...
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* ============================================================ */}
          {/* RIGHT SIDE: RESULTS */}
          {/* ============================================================ */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            <AnimatePresence mode="wait">
              {analysisResult ? (
                <motion.div
                  key="results"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 20 }}
                  className="space-y-6"
                >
                  <div>
                    <h2 className="text-2xl sm:text-3xl font-bold mb-2">Analysis Results</h2>
                    <p className="text-sm text-slate-400">Here's what our AI found</p>
                  </div>

                  {/* Match Score Card with Animation */}
                  <motion.div
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.3 }}
                    className={`relative group rounded-2xl backdrop-blur-xl border-2 p-8 overflow-hidden transition-all duration-300 ${
                      analysisResult.match_score >= 75
                        ? 'bg-gradient-to-br from-green-500/10 to-emerald-500/10 border-green-500/30 group-hover:border-green-500/50'
                        : analysisResult.match_score >= 50
                        ? 'bg-gradient-to-br from-yellow-500/10 to-amber-500/10 border-yellow-500/30 group-hover:border-yellow-500/50'
                        : 'bg-gradient-to-br from-red-500/10 to-rose-500/10 border-red-500/30 group-hover:border-red-500/50'
                    }`}
                  >
                    <div className="absolute inset-0 opacity-0 group-hover:opacity-50 transition-opacity duration-300 bg-gradient-to-br from-white/10 to-transparent"></div>
                    <div className="relative flex flex-col items-center">
                      <p className="text-xs sm:text-sm font-semibold tracking-widest text-slate-400 mb-6">
                        MATCH SCORE
                      </p>
                      <motion.div
                        className={`relative w-32 h-32 sm:w-40 sm:h-40 rounded-full border-4 flex items-center justify-center shadow-2xl ${
                          analysisResult.match_score >= 75
                            ? 'border-green-400/40 bg-green-500/5'
                            : analysisResult.match_score >= 50
                            ? 'border-yellow-400/40 bg-yellow-500/5'
                            : 'border-red-400/40 bg-red-500/5'
                        }`}
                        animate={{ scale: [1, 1.05, 1] }}
                        transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
                      >
                        <div className="text-center">
                          <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            transition={{ delay: 0.4 }}
                            className={`text-4xl sm:text-6xl font-black ${
                              analysisResult.match_score >= 75
                                ? 'text-green-400'
                                : analysisResult.match_score >= 50
                                ? 'text-yellow-400'
                                : 'text-red-400'
                            }`}
                          >
                            <AnimatedCounter value={analysisResult.match_score} />
                          </motion.div>
                          <p className="text-slate-400 text-xs sm:text-sm mt-2 font-medium">%</p>
                        </div>
                      </motion.div>

                      <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.6 }}
                        className="mt-8 text-center"
                      >
                        <p className="text-sm sm:text-base font-semibold">
                          {analysisResult.match_score >= 75
                            ? '🟢 Excellent Match'
                            : analysisResult.match_score >= 50
                            ? '🟡 Good Fit'
                            : '🔴 Needs Development'}
                        </p>
                        <p className="text-xs text-slate-400 mt-2">
                          {analysisResult.match_score >= 75
                            ? 'Highly recommended for interview'
                            : analysisResult.match_score >= 50
                            ? 'Consider for next round'
                            : 'May benefit from additional training'}
                        </p>
                      </motion.div>
                    </div>
                  </motion.div>

                  {/* Key Strengths */}
                  {analysisResult.key_strengths && analysisResult.key_strengths.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.4 }}
                      className="backdrop-blur-xl bg-white/5 border border-white/20 rounded-xl p-6 hover:border-white/40 transition-all duration-300"
                    >
                      <h3 className="font-semibold mb-4 flex items-center gap-2 text-green-400">
                        <TrendingUp className="w-5 h-5" />
                        Key Strengths
                      </h3>
                      <div className="space-y-2">
                        {analysisResult.key_strengths.map((strength, idx) => (
                          <motion.div
                            key={idx}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: 0.5 + idx * 0.1 }}
                            className="flex items-start gap-3 p-2"
                          >
                            <div className="pt-1 text-green-400">✓</div>
                            <p className="text-slate-300 text-sm">{strength}</p>
                          </motion.div>
                        ))}
                      </div>
                    </motion.div>
                  )}

                  {/* Summary */}
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5 }}
                    className="glass-card-strong rounded-xl p-6 shadow-lg hover:shadow-blue-500/10 transition-all duration-300"
                  >
                    <h3 className="font-semibold mb-3 flex items-center gap-2">
                      <CheckCircle className="w-5 h-5 text-blue-400" />
                      AI Summary
                    </h3>
                    <p className="text-slate-300 leading-relaxed text-sm">
                      {analysisResult.summary}
                    </p>
                  </motion.div>

                  {/* Missing Skills */}
                  {analysisResult.missing_skills && analysisResult.missing_skills.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.6 }}
                      className="glass-card-strong rounded-xl p-6 shadow-lg hover:shadow-orange-500/10 transition-all duration-300"
                    >
                      <h3 className="font-semibold mb-4 flex items-center gap-2 text-orange-400">
                        <AlertCircle className="w-5 h-5" />
                        Skills to Develop
                      </h3>
                      <div className="flex flex-wrap gap-2">
                        {analysisResult.missing_skills.map((skill, idx) => (
                          <motion.span
                            key={idx}
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.6 + idx * 0.1 }}
                            className="px-3 py-2 bg-gradient-to-r from-orange-500/20 to-red-500/20 border border-orange-500/40 text-orange-300 rounded-full text-xs font-semibold hover:border-orange-500/60 transition-all cursor-default"
                          >
                            {skill}
                          </motion.span>
                        ))}
                      </div>
                    </motion.div>
                  )}

                  {/* Email Draft */}
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.7 }}
                    className="backdrop-blur-xl bg-white/5 border border-white/20 rounded-xl p-6 hover:border-white/40 transition-all duration-300"
                  >
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="font-semibold">Interview Email</h3>
                      <motion.button
                        onClick={copyToClipboard}
                        whileHover={{ scale: 1.05 }}
                        whileTap={{ scale: 0.95 }}
                        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                          copied
                            ? 'bg-green-500/20 text-green-400 border border-green-500/40'
                            : 'bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:border-blue-500/50'
                        }`}
                      >
                        <Copy className="w-4 h-4" />
                        {copied ? 'Copied!' : 'Copy'}
                      </motion.button>
                    </div>
                    <textarea
                      value={analysisResult.email_draft}
                      readOnly
                      className="w-full h-32 sm:h-40 px-4 py-3 bg-slate-950/50 border border-white/10 rounded-lg text-slate-300 font-mono text-xs resize-none focus:outline-none"
                    />
                  </motion.div>

                  {/* New Analysis Button */}
                  <motion.button
                    onClick={() => {
                      setAnalysisResult(null);
                      setResumeFile(null);
                      setJobDescription('');
                    }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    className="w-full py-3 bg-white/5 hover:bg-white/10 border border-white/20 hover:border-white/40 rounded-xl font-semibold text-white transition-all duration-300 backdrop-blur-xl"
                  >
                    Analyze Another Candidate
                  </motion.button>
                </motion.div>
              ) : (
                <motion.div
                  key="empty"
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 20 }}
                  className="h-full min-h-96 sm:min-h-[500px] flex flex-col items-center justify-center backdrop-blur-xl bg-white/5 border-2 border-dashed border-white/20 rounded-2xl p-8"
                >
                  <motion.div
                    animate={{ y: [0, -12, 0] }}
                    transition={{ duration: 3, repeat: Infinity }}
                  >
                    <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-full bg-gradient-to-br from-blue-500/20 to-cyan-500/20 flex items-center justify-center mb-6">
                      <Zap className="w-10 h-10 sm:w-12 sm:h-12 text-blue-400" />
                    </div>
                  </motion.div>
                  <h3 className="text-xl sm:text-2xl font-bold text-slate-100 mb-2">
                    Ready to Evaluate
                  </h3>
                  <p className="text-slate-400 text-sm text-center max-w-xs">
                    Upload a resume and job description to get AI-powered candidate insights
                  </p>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </div>

      {/* Premium Footer */}
      <footer className="relative mt-20 border-t border-white/5">
        {/* Glow effect behind footer */}
        <div className="absolute inset-0 bg-gradient-to-t from-blue-500/5 to-transparent pointer-events-none"></div>
        
        <div className="relative max-w-7xl mx-auto px-6 py-12">
          <div className="glass-card rounded-2xl p-8">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
              {/* Brand Column */}
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center shadow-lg shadow-blue-500/30">
                    <Zap className="w-6 h-6 text-white" />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white">SmartHire</h3>
                    <p className="text-xs text-slate-400">AI Candidate Intelligence</p>
                  </div>
                </div>
                <p className="text-sm text-slate-400 leading-relaxed">
                  Lightning-fast resume analysis powered by Groq AI's LPU technology. 
                  Evaluate candidate fit in under 2 seconds.
                </p>
              </div>

              {/* Tech Stack Column */}
              <div className="space-y-4">
                <h4 className="text-sm font-semibold text-white uppercase tracking-wider">Powered By</h4>
                <div className="space-y-3">
                  <div className="flex items-center gap-3 text-sm">
                    <div className="w-8 h-8 bg-purple-500/10 rounded-lg flex items-center justify-center">
                      <svg className="w-4 h-4 text-purple-400" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M13 7H7v6h6V7z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-white font-medium">Groq AI</p>
                      <p className="text-xs text-slate-500">Llama 3.3 70B</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 text-sm">
                    <div className="w-8 h-8 bg-blue-500/10 rounded-lg flex items-center justify-center">
                      <span className="text-blue-400 font-bold text-xs">⚛</span>
                    </div>
                    <div>
                      <p className="text-white font-medium">React + FastAPI</p>
                      <p className="text-xs text-slate-500">Modern Stack</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Developer Column */}
              <div className="space-y-4">
                <h4 className="text-sm font-semibold text-white uppercase tracking-wider">Created By</h4>
                <div className="flex items-start gap-4">
                  <div className="relative">
                    <div className="w-16 h-16 bg-gradient-to-br from-blue-500 via-purple-500 to-cyan-500 rounded-2xl flex items-center justify-center shadow-xl">
                      <span className="text-white font-bold text-2xl">AG</span>
                    </div>
                    <div className="absolute -bottom-1 -right-1 w-5 h-5 bg-emerald-500 rounded-full border-2 border-slate-900 flex items-center justify-center">
                      <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </div>
                  <div>
                    <h5 className="text-white font-bold text-lg">Abdullah Ghaffar</h5>
                    <p className="text-sm text-slate-400 mb-3">Full-Stack AI Engineer</p>
                    <div className="flex gap-2">
                      <a href="https://github.com/abdullahghaffar9" target="_blank" rel="noopener noreferrer"
                         className="w-8 h-8 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg flex items-center justify-center transition-all hover:scale-110">
                        <svg className="w-4 h-4 text-slate-300" fill="currentColor" viewBox="0 0 24 24">
                          <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
                        </svg>
                      </a>
                      <a href="https://www.linkedin.com/in/abdullahghaffar" target="_blank" rel="noopener noreferrer"
                         className="w-8 h-8 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg flex items-center justify-center transition-all hover:scale-110">
                        <svg className="w-4 h-4 text-slate-300" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
                        </svg>
                      </a>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Bottom Bar */}
            <div className="pt-6 border-t border-white/5 flex flex-col sm:flex-row items-center justify-between gap-4">
              <p className="text-sm text-slate-500">
                © 2026 SmartHire by <span className="text-blue-400 font-medium">Abdullah Ghaffar</span>. All rights reserved.
              </p>
              <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                <span className="text-xs text-emerald-300 font-medium">System Operational</span>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
