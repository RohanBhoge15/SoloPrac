import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import {
  Stethoscope, Users, FileText, Brain, Mic, Shield, Calendar,
  ArrowRight, CheckCircle, ScanLine, Activity, ChevronRight,
  Sparkles, Lock, Globe
} from 'lucide-react'

const FEATURES = [
  {
    icon: Brain,
    title: 'AI-Powered Prescriptions',
    description: 'Handwriting-aware OCR extracts text from handwritten prescriptions. AI structures it into clean, professional prescriptions.',
  },
  {
    icon: FileText,
    title: 'Version-Controlled Records',
    description: 'Every edit creates an immutable, content-addressed version. Full audit trail — who changed what, when, and why.',
  },
  {
    icon: Mic,
    title: 'Voice-to-Text',
    description: 'Dictate notes, diagnoses, and instructions. Multilingual ASR with Hindi support for faster documentation.',
  },
  {
    icon: ScanLine,
    title: 'Smart Document Parsing',
    description: 'Upload any document — PDFs, lab reports, discharge summaries. Auto-classified and indexed for instant retrieval.',
  },
  {
    icon: Activity,
    title: 'Clinical Decision Support',
    description: 'Temporal-aware RAG retrieves relevant patient history. Risk scoring flags chronic conditions early.',
  },
  {
    icon: Calendar,
    title: 'Appointment Management',
    description: 'Online booking for patients. Conflict-free scheduling with telemedicine consent tracking.',
  },
]

const HOW_IT_WORKS = [
  {
    step: '01',
    title: 'Register as a Doctor',
    description: 'Sign up with your email, verify your NMC registration. Set up your clinic in under 2 minutes.',
  },
  {
    step: '02',
    title: 'Start Seeing Patients',
    description: 'Upload handwritten prescriptions, dictate notes, or type directly. AI handles the documentation.',
  },
  {
    step: '03',
    title: 'Patients Book Online',
    description: 'Patients find you via search, book appointments, and receive digital prescriptions — all from their phone.',
  },
]

const STATS = [
  { value: '<2 min', label: 'Average setup time' },
  { value: '100%', label: 'India-compliant (DPDP Act)' },
  { value: 'Free', label: 'Core features forever' },
]

export function Landing() {
  return (
    <div className="min-h-screen bg-white dark:bg-gray-950">
      {/* ── Navbar ── */}
      <nav className="sticky top-0 z-50 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary-600 flex items-center justify-center">
              <Stethoscope className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-bold text-gray-900 dark:text-white">SoloPrac AI</span>
          </div>
          <div className="flex items-center gap-3">
            <Link to="/login">
              <Button variant="ghost" size="sm">Doctor Login</Button>
            </Link>
            <Link to="/patient/login">
              <Button variant="ghost" size="sm">Patient Login</Button>
            </Link>
            <Link to="/register">
              <Button size="sm">Get Started</Button>
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-primary-50 via-white to-blue-50 dark:from-gray-900 dark:via-gray-950 dark:to-gray-900" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 sm:py-32">
          <div className="text-center max-w-3xl mx-auto">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 text-sm font-medium mb-6">
              <Sparkles className="h-4 w-4" />
              Built for India's Solo Doctors
            </div>
            <h1 className="text-4xl sm:text-6xl font-bold text-gray-900 dark:text-white tracking-tight">
              Your Clinic's AI
              <span className="text-primary-600"> Operating System</span>
            </h1>
            <p className="mt-6 text-lg sm:text-xl text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
              SoloPrac AI turns your smartphone into a clinical workstation.
              Upload handwritten prescriptions, dictate notes, manage patients —
              AI handles the documentation so you can focus on medicine.
            </p>
            <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link to="/register">
                <Button size="lg" className="text-base px-8">
                  Register as Doctor
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Button>
              </Link>
              <Link to="/patient/register">
                <Button variant="outline" size="lg" className="text-base px-8">
                  Register as Patient
                  <ChevronRight className="ml-2 h-5 w-5" />
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Stats ── */}
      <section className="border-y border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {STATS.map((stat, i) => (
              <div key={i} className="text-center">
                <div className="text-2xl font-bold text-primary-600">{stat.value}</div>
                <div className="text-sm text-gray-500 dark:text-gray-400 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── For Doctors / For Patients ── */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Doctor Card */}
          <Card className="relative overflow-hidden border-2 hover:border-primary-500 transition-colors">
            <CardContent className="p-8">
              <div className="h-12 w-12 rounded-xl bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center mb-5">
                <Stethoscope className="h-6 w-6 text-primary-600" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">For Doctors</h3>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Solo practitioners managing their own clinic. One doctor, one clinic, zero paperwork.
              </p>
              <ul className="space-y-3 mb-8">
                {[
                  'AI-powered prescription writing from handwriting',
                  'Version-controlled patient records with full audit trail',
                  'Voice-to-text for notes in English & Hindi',
                  'Online appointment booking for patients',
                  'Weekly clinical reports with AI insights',
                  'DPDP Act compliant — data stays in India',
                ].map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <CheckCircle className="h-4 w-4 text-primary-600 mt-0.5 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
              <Link to="/register">
                <Button className="w-full">
                  Register as Doctor
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>

          {/* Patient Card */}
          <Card className="relative overflow-hidden border-2 hover:border-blue-500 transition-colors">
            <CardContent className="p-8">
              <div className="h-12 w-12 rounded-xl bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center mb-5">
                <Users className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-3">For Patients</h3>
              <p className="text-gray-600 dark:text-gray-400 mb-6">
                Find trusted doctors, book appointments, and access your medical records — all in one place.
              </p>
              <ul className="space-y-3 mb-8">
                {[
                  'Search doctors by specialty, location, or PIN code',
                  'Book appointments with telemedicine consent',
                  'View prescriptions, invoices, and reports',
                  'Download PDFs of all your medical documents',
                  'Timeline view of your complete medical history',
                  'Secure — your data is encrypted and private',
                ].map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <CheckCircle className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
              <Link to="/patient/register">
                <Button variant="outline" className="w-full border-blue-300 dark:border-blue-700 text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/20">
                  Register as Patient
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="bg-gray-50 dark:bg-gray-900/50 border-y border-gray-200 dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 dark:text-white">Everything You Need</h2>
            <p className="mt-3 text-gray-600 dark:text-gray-400 max-w-xl mx-auto">
              Purpose-built for solo medical practitioners in India. No bloat, no enterprise features — just what you need.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {FEATURES.map((feature, i) => (
              <Card key={i} className="hover:shadow-md transition-shadow">
                <CardContent className="p-6">
                  <div className="h-10 w-10 rounded-lg bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center mb-4">
                    <feature.icon className="h-5 w-5 text-primary-600" />
                  </div>
                  <h3 className="font-semibold text-gray-900 dark:text-white mb-2">{feature.title}</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{feature.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white">Get Started in 3 Steps</h2>
          <p className="mt-3 text-gray-600 dark:text-gray-400">
            From sign-up to your first AI-assisted prescription — under 2 minutes.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {HOW_IT_WORKS.map((step, i) => (
            <div key={i} className="text-center">
              <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary-600 text-white text-xl font-bold mb-4">
                {step.step}
              </div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">{step.title}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-400">{step.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Compliance ── */}
      <section className="bg-gray-50 dark:bg-gray-900/50 border-y border-gray-200 dark:border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            <div className="flex items-start gap-3">
              <Shield className="h-6 w-6 text-primary-600 mt-1 shrink-0" />
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white">DPDP Act Compliant</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  Full consent management, data erasure rights, and purpose limitation — India's data protection law built in.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Lock className="h-6 w-6 text-primary-600 mt-1 shrink-0" />
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white">End-to-End Encrypted</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  PII encrypted at rest, HttpOnly cookies, RBAC — your patients' data is always protected.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Globe className="h-6 w-6 text-primary-600 mt-1 shrink-0" />
              <div>
                <h4 className="font-semibold text-gray-900 dark:text-white">Made for India</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  State-specific prescriptions, NMC verification, Indian drug names, Hindi UI — built for how Indian doctors actually work.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="text-center">
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white">
            Ready to modernize your practice?
          </h2>
          <p className="mt-3 text-gray-600 dark:text-gray-400 max-w-lg mx-auto">
            Join doctors who are already using AI to save 2+ hours daily on documentation.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/register">
              <Button size="lg" className="text-base px-8">
                Register as Doctor
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
            </Link>
            <Link to="/patient/register">
              <Button variant="outline" size="lg" className="text-base px-8">
                Register as Patient
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="h-6 w-6 rounded bg-primary-600 flex items-center justify-center">
                <Stethoscope className="h-3.5 w-3.5 text-white" />
              </div>
              <span className="text-sm font-semibold text-gray-900 dark:text-white">SoloPrac AI</span>
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              BTech Capstone Project · IEEE Paper · Made in India
            </p>
          </div>
        </div>
      </footer>
    </div>
  )
}
