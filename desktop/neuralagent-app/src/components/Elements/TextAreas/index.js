import React from 'react';
import {
  LabeledTAContainer,
  VerticalLabeledTAContainer,
  TextAreaLabel,
  TextArea,
  TextAreaError
} from './Elements';

const NATextArea = ({
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
  onChange,
  rows='4',
  onKeyDown
}) => {
  if (label !== null) {
    if (!verticalLabel) {
      return (
        <>
          <LabeledTAContainer>
            <TextAreaLabel fontSize={fontSize} fontWeight={labelFontWeight} isDarkMode={isDarkMode}>
              {label}
            </TextAreaLabel>
            <div style={{flex: '1 1 75%'}}>
              <TextArea background={background} fontSize={fontSize} placeholder={placeholder} padding={padding}
                rows={rows} cols="50"
                isDarkMode={isDarkMode}
                onKeyDown={onKeyDown}
                borderRadius={borderRadius} outlined={outlined} value={value} onChange={onChange} />
              {
                error !== null ?
                <TextAreaError>
                  {error}
                </TextAreaError> :
                <></>
              }
            </div>
          </LabeledTAContainer>
        </>
      );
    } else {
      return (
        <>
          <VerticalLabeledTAContainer>
            <TextAreaLabel verticalLabel fontSize={fontSize} fontWeight={labelFontWeight} isDarkMode={isDarkMode}>
              {label}
            </TextAreaLabel>
            <TextArea background={background} fontSize={fontSize} placeholder={placeholder} padding={padding}
              rows={rows} cols="50"
              isDarkMode={isDarkMode}
              onKeyDown={onKeyDown}
              borderRadius={borderRadius} outlined={outlined} value={value} onChange={onChange} />
            {
              error !== null ?
              <TextAreaError>
                {error}
              </TextAreaError> :
              <></>
            }
          </VerticalLabeledTAContainer>
        </>
      );
    }
  }
  return (
    <>
      <TextArea background={background} fontSize={fontSize} placeholder={placeholder} padding={padding}
        rows={rows} cols="50"
        isDarkMode={isDarkMode}
        onKeyDown={onKeyDown}
        borderRadius={borderRadius} outlined={outlined} value={value} onChange={onChange} />
      <TextAreaError>
        {error}
      </TextAreaError>
    </>
  );
};

export default NATextArea;
