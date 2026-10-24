import { redirect } from 'next/navigation'

// Today is the home screen (docs/SPEC.md section 9.1).
export default function Home() {
  redirect('/today')
}
