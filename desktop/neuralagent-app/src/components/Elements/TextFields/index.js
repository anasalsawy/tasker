import React from 'react';
import {
  LabeledTFContainer,
  VerticalLabeledTFContainer,
  TextFieldLabel,
  TextField,
  TextFieldError
} from './Elements';

const NATextField = ({
  label=null,
  verticalLabel=false,
  fontSize='16px',
  labelFontWeight='500',
  error=null,
  background='#fff',
  outlined=false,
  padding=null,
  borderRadius=null,
  placeholder=null,
  value=null,
  isDarkMode=false,
  type='text',
  autoFocus=false,
  onChange,
  onFocus
}) => {
  if (label !== null) {
    if (!verticalLabel) {
      return (
        <>
          <LabeledTFContainer>
            <TextFieldLabel fontSize={fontSize} fontWeight={labelFontWeight} isDarkMode={isDarkMode}>
              {label}
            </TextFieldLabel>
            <div style={{flex: '1 1 75%'}}>
              <TextField background={background} placeholder={placeholder} padding={padding} fontSize={fontSize}
                borderRadius={borderRadius} outlined={outlined} value={value} onFocus={onFocus} onChange={onChange}
                type={type} autoFocus={autoFocus} isDarkMode={isDarkMode} />
              {
                error !== null ?
                <TextFieldError>
                  {error}
                </TextFieldError> :
                <></>
              }
            </div>
          </LabeledTFContainer>
        </>
      );
    } else {
      return (
        <>
          <VerticalLabeledTFContainer>
            <TextFieldLabel verticalLabel fontSize={fontSize} fontWeight={labelFontWeight} isDarkMode={isDarkMode}>
              {label}
            </TextFieldLabel>
            <TextField style={{marginTop: '6px'}} background={background} placeholder={placeholder} padding={padding} fontSize={fontSize}
              borderRadius={borderRadius} outlined={outlined} value={value} onFocus={onFocus} onChange={onChange} type={type} autoFocus={autoFocus}
              isDarkMode={isDarkMode} />
            {
              error !== null ?
              <TextFieldError>
                {error}
              </TextFieldError> :
              <></>
            }
          </VerticalLabeledTFContainer>
        </>
      );
    }
  }
  return (
    <>
      <TextField background={background} placeholder={placeholder} padding={padding} fontSize={fontSize}
        borderRadius={borderRadius} outlined={outlined} value={value} onFocus={onFocus} onChange={onChange}
        type={type} autoFocus={autoFocus} isDarkMode={isDarkMode} />
      <TextFieldError>
        {error}
      </TextFieldError>
    </>
  );
};

export default NATextField;
