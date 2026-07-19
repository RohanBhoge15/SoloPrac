import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { TimelineScrubber, type VersionNode } from '@/components/TimelineScrubber'
import { ContextPanel } from '@/components/ContextPanel'
import { ChatUI } from '@/components/ChatUI'
import { Edit, Plus, Clock, FileText, ArrowUpDown, Search, Save, X, Check, Loader2 } from 'lucide-react'

const MOCK_VERSIONS: VersionNode[] = [
  { id: 'v1', version_number: 3, author: 'doctor:1', edit_type: 'manual', summary: 'Updated phone number', tags: ['phone'], clinical_significance: 0.3, timestamp: '2026-07-18T10:30:00Z' },
  { id: 'v2', version_number: 2, author: 'agent:rag', edit_type: 'ai_suggestion', summary: 'Added HbA1c from lab report', tags: ['lab'], clinical_significance: 0.8, timestamp: '2026-07-15T14:20:00Z' },
  { id: 'v3', version_number: 1, author: 'doctor:1', edit_type: 'manual', summary: 'Initial patient record', tags: ['demographics'], clinical_significance: 1.0, timestamp: '2026-07-01T09:00:00Z' },
]

interface Demographics {
  name: string
  age: number
  gender: string
  phone: string
  email: string
  address: string
  dob: string
}

export function PatientDetail() {
  const { id } = useParams()
  const [activeVersion, setActiveVersion] = useState<number | null>(null)
  const [showTimeline, setShowTimeline] = useState(true)
  const [showContextPanel, setShowContextPanel] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [editedFields, setEditedFields] = useState<Partial<Demographics>>({})

  const [demographics, setDemographics] = useState<Demographics>({
    name: 'Priya Sharma',
    age: 45,
    gender: 'Female',
    phone: '+91-9876543210',
    email: 'priya.sharma@email.com',
    address: 'Flat 302, Sunrise Apartments, Aundh, Pune',
    dob: '1979-03-15',
  })

  const diagnoses = ['Type 2 Diabetes Mellitus', 'Hypertension']
  const medications = [
    { drug: 'Metformin', strength: '500 mg', dose: '1 tab', frequency: 'BD' },
    { drug: 'Amlodipine', strength: '5 mg', dose: '1 tab', frequency: 'OD' },
  ]

  const handleSelectVersion = (versionNumber: number) => {
    setActiveVersion(versionNumber)
  }

  const handleCompare = (_v1: number, v2: number) => {
    setActiveVersion(v2)
  }

  const handleCiteVersion = (versionNumber: number) => {
    setActiveVersion(versionNumber)
    // Scroll to timeline
    const el = document.querySelector('[data-ver="' + versionNumber + '"]')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const toggleEditMode = () => {
    if (editMode) {
      // Cancel edit
      setEditMode(false)
      setEditedFields({})
    } else {
      setEditMode(true)
    }
  }

  const handleFieldEdit = (field: keyof Demographics, value: string) => {
    setEditedFields(prev => ({ ...prev, [field]: value }))
  }

  const handleSaveEdit = async () => {
    setSaving(true)
    // Simulate API call
    await new Promise(r => setTimeout(r, 1000))
    setDemographics(prev => ({ ...prev, ...editedFields }))
    setSaving(false)
    setEditMode(false)
    setEditedFields({})
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  const displayDemographics: Demographics = { ...demographics, ...editedFields }

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header with patient info */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                <span className="text-2xl font-bold text-primary-700 dark:text-primary-300">
                  {demographics.name.split(' ').map(n => n[0]).join('')}
                </span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{displayDemographics.name}</h1>
                <p className="text-gray-500 dark:text-gray-400">{displayDemographics.age} years &bull; {displayDemographics.gender} &bull; ID: {id}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {editMode ? (
                <>
                  <Button variant="outline" onClick={toggleEditMode} disabled={saving}>
                    <X className="h-4 w-4 mr-2" />Cancel
                  </Button>
                  <Button onClick={handleSaveEdit} disabled={saving || Object.keys(editedFields).length === 0}>
                    {saving ? (
                      <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving...</>
                    ) : saved ? (
                      <><Check className="h-4 w-4 mr-2" />Saved!</>
                    ) : (
                      <><Save className="h-4 w-4 mr-2" />Save Changes</>
                    )}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" onClick={() => setShowTimeline(!showTimeline)}>
                    <Clock className="h-4 w-4 mr-2" />Timeline
                  </Button>
                  <Button variant="outline" onClick={toggleEditMode}>
                    <Edit className="h-4 w-4 mr-2" />Edit Fields
                  </Button>
                  <Button onClick={() => setShowContextPanel(!showContextPanel)}>
                    <Plus className="h-4 w-4 mr-2" />Context
                  </Button>
                </>
              )}
            </div>
          </div>

          {/* Timeline Scrubber */}
          {showTimeline && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <TimelineScrubber
                versions={MOCK_VERSIONS}
                activeVersion={activeVersion}
                onSelectVersion={handleSelectVersion}
                onCompare={handleCompare}
              />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Main Content + Right Rail */}
      <div className="flex gap-6">
        <div className="flex-1 min-w-0">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="images">Images</TabsTrigger>
              <TabsTrigger value="documents">Documents</TabsTrigger>
              <TabsTrigger value="chat">AI Chat</TabsTrigger>
            </TabsList>

            {/* Overview Tab */}
            <TabsContent value="overview" className="space-y-6 mt-4">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Demographics */}
                <Card className="lg:col-span-1">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Clock className="h-5 w-5 text-primary-600" />
                      Demographics
                      {editMode && (
                        <Badge variant="secondary" className="ml-auto text-[10px]">Editing</Badge>
                      )}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {Object.entries(displayDemographics).map(([k, v]) => (
                      <div key={k} className="flex justify-between items-center">
                        <span className="text-sm text-gray-500 dark:text-gray-400 capitalize">{k.replace('_', ' ')}</span>
                        {editMode ? (
                          <Input
                            defaultValue={String(v)}
                            onChange={(e) => handleFieldEdit(k as keyof Demographics, e.target.value)}
                            className="w-40 h-7 text-xs text-right"
                          />
                        ) : (
                          <span className="font-medium text-gray-900 dark:text-white text-sm">{String(v)}</span>
                        )}
                      </div>
                    ))}
                  </CardContent>
                </Card>

                {/* Clinical */}
                <Card className="lg:col-span-2">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <FileText className="h-5 w-5 text-primary-600" />
                      Clinical Summary
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-white mb-2">Diagnoses</h4>
                      <div className="flex flex-wrap gap-2">
                        {diagnoses.map((d, i) => (
                          <Badge key={i} variant="default" className="bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                            {d}
                          </Badge>
                        ))}
                      </div>
                    </div>
                    <div>
                      <h4 className="font-medium text-gray-900 dark:text-white mb-2">Current Medications</h4>
                      <div className="space-y-2">
                        {medications.map((m, i) => (
                          <div key={i} className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                            <div className="flex-1">
                              <p className="font-medium text-gray-900 dark:text-white">{m.drug} {m.strength}</p>
                              <p className="text-sm text-gray-500 dark:text-gray-400">{m.dose} &bull; {m.frequency}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* Timeline Tab */}
            <TabsContent value="timeline" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Version History</CardTitle>
                </CardHeader>
                <CardContent>
                  <TimelineScrubber
                    versions={MOCK_VERSIONS}
                    activeVersion={activeVersion}
                    onSelectVersion={handleSelectVersion}
                    onCompare={handleCompare}
                  />
                  <div className="mt-6 space-y-4">
                    {MOCK_VERSIONS.map((v) => (
                      <div
                        key={v.version_number}
                        className={cn(
                          'flex items-start gap-4 p-4 rounded-lg border transition-colors cursor-pointer',
                          activeVersion === v.version_number
                            ? 'border-primary-300 dark:border-primary-700 bg-primary-50 dark:bg-primary-900/10'
                            : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50'
                        )}
                        onClick={() => handleSelectVersion(v.version_number)}
                      >
                        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                          <ArrowUpDown className="h-5 w-5 text-primary-700 dark:text-primary-300" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-3">
                            <span className="font-medium text-gray-900 dark:text-white">Version {v.version_number}</span>
                            <Badge variant="secondary" className="text-xs">
                              {v.edit_type}
                            </Badge>
                            <Badge variant="outline" className="text-xs">
                              {v.author}
                            </Badge>
                          </div>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">{v.summary}</p>
                          <p className="text-xs text-gray-400 mt-1">{new Date(v.timestamp).toLocaleString()}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button variant="ghost" size="icon" title="View this version"><Search className="h-4 w-4" /></Button>
                          <Button variant="ghost" size="icon" title="Compare"><ArrowUpDown className="h-4 w-4" /></Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Images Tab */}
            <TabsContent value="images" className="mt-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle>Wound / Skin Images</CardTitle>
                  <Button>Upload Photo</Button>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {[
                      { url: 'https://via.placeholder.com/300x200', date: 'Jul 15', label: 'Initial wound' },
                      { url: 'https://via.placeholder.com/300x200', date: 'Jul 18', label: 'Follow-up' },
                    ].map((img, i) => (
                      <div key={i} className="relative group">
                        <img src={img.url} alt={img.label} className="w-full aspect-video object-cover rounded-lg" />
                        <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center text-white">
                          <p className="font-medium">{img.label}</p>
                          <p className="text-sm text-gray-300">{img.date}</p>
                          <Button variant="ghost" className="mt-2 text-white border-white hover:bg-white/20">Compare</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Documents Tab */}
            <TabsContent value="documents" className="mt-4">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle>Documents</CardTitle>
                  <Button>Upload</Button>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {[
                      { name: 'Lab Report - HbA1c.pdf', type: 'lab', date: 'Jul 15', size: '245 KB' },
                      { name: 'Prescription - Jun 20.pdf', type: 'prescription', date: 'Jun 20', size: '180 KB' },
                      { name: 'Referral Letter.pdf', type: 'referral', date: 'May 10', size: '310 KB' },
                    ].map((doc, i) => (
                      <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                        <div className="flex items-center gap-3">
                          <FileText className="h-8 w-8 text-primary-600" />
                          <div>
                            <p className="font-medium text-gray-900 dark:text-white">{doc.name}</p>
                            <p className="text-sm text-gray-500 dark:text-gray-400">{doc.type} &bull; {doc.date} &bull; {doc.size}</p>
                          </div>
                        </div>
                        <Button variant="ghost" size="icon">View</Button>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Chat / AI Assistant integrated tab */}
            <TabsContent value="chat" className="mt-4">
              <Card className="h-[500px]">
                <CardContent className="p-0 h-full">
                  <ChatUI
                    patientId={id}
                    onCiteVersion={handleCiteVersion}
                    initialMessage="Ask me about this patient's records. I can search their version history using temporal-aware RAG."
                  />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>

        {/* Right Rail — Context Panel */}
        {showContextPanel && (
          <div className="w-72 shrink-0 hidden xl:block">
            <div className="sticky top-24">
              <ContextPanel
                patient={{
                  name: demographics.name,
                  age: demographics.age,
                  gender: demographics.gender,
                  id: id || '',
                }}
                vitals={{
                  bp_systolic: 140,
                  bp_diastolic: 90,
                  heart_rate: 78,
                  weight: 72,
                  date: '2026-07-15',
                }}
                medications={medications}
                diagnoses={diagnoses}
                nextAppointment={{
                  date: '2026-07-25 at 10:00 AM',
                  reason: 'Diabetes follow-up',
                }}
                alerts={[
                  { severity: 'high', message: 'HbA1c rising 0.5% in 90 days' },
                  { severity: 'low', message: 'Patient due for annual review' },
                ]}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
