import { useParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/Tabs'
import { Edit, Plus, Clock, FileText, ArrowUpDown, Search } from 'lucide-react'

const MOCK_VERSIONS = [
  { number: 3, author: 'doctor:1', edit_type: 'manual', summary: 'Updated phone number', timestamp: '2026-07-18T10:30:00Z', tags: ['phone'] },
  { number: 2, author: 'agent:rag', edit_type: 'ai_suggestion', summary: 'Added HbA1c from lab report', timestamp: '2026-07-15T14:20:00Z', tags: ['lab'] },
  { number: 1, author: 'doctor:1', edit_type: 'manual', summary: 'Initial patient record', timestamp: '2026-07-01T09:00:00Z', tags: ['demographics'] },
]

const MOCK_PATIENT_STATE = {
  demographics: {
    name: 'Priya Sharma',
    age: 45,
    gender: 'Female',
    phone: '+91-9876543210',
    email: 'priya.sharma@email.com',
    address: 'Flat 302, Sunrise Apartments, Aundh, Pune',
    dob: '1979-03-15',
  },
  clinical: {
    diagnoses: ['Type 2 Diabetes Mellitus', 'Hypertension'],
    medications: [
      { drug: 'Metformin', strength: '500 mg', dose: '1 tab', frequency: 'BD', duration: '30 days' },
      { drug: 'Amlodipine', strength: '5 mg', dose: '1 tab', frequency: 'OD', duration: '30 days' },
    ],
    vitals: [
      { date: '2026-07-15', bp: '140/90', hr: 78, weight: 72 },
      { date: '2026-06-20', bp: '135/85', hr: 76, weight: 73 },
    ],
  },
}

export function PatientDetail() {
  const { id } = useParams()

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Header with patient info */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="h-16 w-16 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                <span className="text-2xl font-bold text-primary-700 dark:text-primary-300">PS</span>
              </div>
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Priya Sharma</h1>
                <p className="text-gray-500 dark:text-gray-400">45 years &bull; Female &bull; ID: {id}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline"><Plus className="h-4 w-4 mr-2" />New Version</Button>
              <Button variant="outline"><Edit className="h-4 w-4 mr-2" />Edit Fields</Button>
              <Button><Plus className="h-4 w-4 mr-2" />Upload Doc</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="images">Images</TabsTrigger>
          <TabsTrigger value="documents">Documents</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6 mt-4">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Demographics */}
            <Card className="lg:col-span-1">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="h-5 w-5 text-primary-600" />
                  Demographics
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {Object.entries(MOCK_PATIENT_STATE.demographics).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-sm text-gray-500 dark:text-gray-400 capitalize">{k.replace('_', ' ')}</span>
                    <span className="font-medium text-gray-900 dark:text-white">{v}</span>
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
                    {MOCK_PATIENT_STATE.clinical.diagnoses.map((d, i) => (
                      <Badge key={i} variant="default" className="bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300">
                        {d}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div>
                  <h4 className="font-medium text-gray-900 dark:text-white mb-2">Current Medications</h4>
                  <div className="space-y-2">
                    {MOCK_PATIENT_STATE.clinical.medications.map((m, i) => (
                      <div key={i} className="p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                        <div className="flex-1">
                          <p className="font-medium text-gray-900 dark:text-white">{m.drug} {m.strength}</p>
                          <p className="text-sm text-gray-500 dark:text-gray-400">{m.dose} &bull; {m.frequency} &bull; {m.duration}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="timeline" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Version History</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {MOCK_VERSIONS.map((v) => (
                  <div key={v.number} className="flex items-start gap-4 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="flex-shrink-0 w-10 h-10 rounded-full bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center">
                      <ArrowUpDown className="h-5 w-5 text-primary-700 dark:text-primary-300" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-3">
                        <span className="font-medium text-gray-900 dark:text-white">Version {v.number}</span>
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
      </Tabs>
    </div>
  )
}