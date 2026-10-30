/** Copy to the clipboard and confirm it with a toast, on every tool page alike. */
export function useCopyText() {
  const toast = useToast()
  return async function copyText(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.add({ title: `${what} copied`, icon: 'i-lucide-check' })
    } catch {
      toast.add({ title: `Could not copy the ${what.toLowerCase()}`, color: 'error', icon: 'i-lucide-circle-x' })
    }
  }
}
