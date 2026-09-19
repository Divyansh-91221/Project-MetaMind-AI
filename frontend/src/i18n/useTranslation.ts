import { useAppContext } from '@/app/appContext';
import { translations, type TranslationKey, type LanguageCode } from './translations';

export function useTranslation() {
  const { language } = useAppContext();
  const langCode = language as LanguageCode;

  const t = (key: TranslationKey, defaultValue?: string): string => {
    const value = translations[langCode]?.[key];
    return value || defaultValue || key;
  };

  return { t, language };
}
