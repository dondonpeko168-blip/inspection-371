import { NextResponse } from 'next/server'

// Credentials are stored as Vercel environment variables for security.
const USER = process.env.BASIC_AUTH_USER
const PASS = process.env.BASIC_AUTH_PASS

export function middleware(request: Request) {
  const authHeader = request.headers.get('authorization')
  // If no Authorization header, request Basic Auth from browser
  if (!authHeader) {
    return new NextResponse('Authentication required', {
      status: 401,
      headers: { 'WWW-Authenticate': 'Basic realm="Protected Area"' },
    })
  }

  // Split "Basic <base64>"
  const [, encoded] = authHeader.split(' ')
  if (!encoded) {
    return new NextResponse('Invalid authentication header', { status: 401 })
  }
  const decoded = Buffer.from(encoded, 'base64').toString()
  const [user, pass] = decoded.split(':')

  // Verify credentials
  if (user === USER && pass === PASS) {
    // Auth succeeded – forward the request to the actual route
    return NextResponse.next()
  }

  // Auth failed – ask again
  return new NextResponse('Invalid credentials', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Protected Area"' },
  })
}
