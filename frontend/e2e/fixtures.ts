// Shared identities for the multi-tenant simulation. A single RUN_ID keeps
// emails/phones unique per run so the suite is re-runnable against a dirty DB.
export const RUN_ID = process.env.RUN_ID || String(Date.now()).slice(-8)

export const PASSWORD = 'TestPass123!'

export type Doc = {
  key: string
  name: string
  email: string
  phone: string
  clinic: string
  address: string
  lat: number
  lng: number
}

export type Pat = {
  key: string
  name: string
  email: string
  phone: string
  dob: string
  gender: string
  address: string
}

// 3 doctors in 3 different cities so geo-search is meaningful.
export const DOCTORS: Doc[] = [
  {
    key: 'A',
    name: 'Dr. Asha Rao',
    email: `dr.asha.${RUN_ID}@clinic.test`,
    phone: `90000${RUN_ID.slice(-5)}`,
    clinic: `Rao Clinic ${RUN_ID}`,
    address: '12 MG Road, Mumbai 400001',
    lat: 19.076,
    lng: 72.8777,
  },
  {
    key: 'B',
    name: 'Dr. Bhaskar Nair',
    email: `dr.bhaskar.${RUN_ID}@clinic.test`,
    phone: `91000${RUN_ID.slice(-5)}`,
    clinic: `Nair Care ${RUN_ID}`,
    address: '5 Brigade Road, Bengaluru 560001',
    lat: 12.9716,
    lng: 77.5946,
  },
  {
    key: 'C',
    name: 'Dr. Chitra Sen',
    email: `dr.chitra.${RUN_ID}@clinic.test`,
    phone: `92000${RUN_ID.slice(-5)}`,
    clinic: `Sen Polyclinic ${RUN_ID}`,
    address: '9 Park Street, Kolkata 700016',
    lat: 22.5726,
    lng: 88.3639,
  },
]

// 10 patients. SHARED is the key isolation subject: they will be registered at
// BOTH doctor A and doctor B, and must never see one clinic's data in the other.
// Distinct surnames, no shared token. A previous version named everyone
// "Patient X Test<n>", so a cross-tenant leak check matching the first name
// token flagged a false positive on the common word "Patient".
const SURNAMES = ['Zephyrin', 'Quillon', 'Vandermolen', 'Okonkwo', 'Blackwood',
                  'Ferreira', 'Nakashima', 'Ostrowski', 'Thibodeaux', 'Yarrowfield']

export const PATIENTS: Pat[] = Array.from({ length: 10 }, (_, i) => {
  const n = i + 1
  return {
    key: `P${n}`,
    name: `${SURNAMES[i]} ${RUN_ID}`,
    email: `patient${n}.${RUN_ID}@mail.test`,
    phone: `98${String(n).padStart(2, '0')}0${RUN_ID.slice(-5)}`,
    dob: `199${n % 10}-0${(n % 9) + 1}-1${n % 10}`,
    gender: ['male', 'female', 'other'][i % 3],
    address: `${n} Test Street, City ${n}`,
  }
})

// The patient who visits two clinics — the isolation subject.
export const SHARED = PATIENTS[0]
